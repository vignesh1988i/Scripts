#!/usr/bin/env python3
"""
Generic Python code for Custom statistics collection for MQ.
MQ 5-Minute Statistics Collector → Prometheus Pushgateway
──────────────────────────────────────────────────────────
Features:
  • Parallel processing of ~80 queue managers using ThreadPoolExecutor
  • One Pushgateway job per queue manager → no metric clashes
  • Uses real 5-min interval end timestamp from amqsvet JSON
  • Sends 0 values for inactive queues → no graph breaks
  • Robust error handling per queue manager
  • Ready for cron every 5 minutes
  
Author: vignesh sundararaman
"""

# ──────────────────────────────────────────────────────────────────────────────
# 1. IMPORTS
# ──────────────────────────────────────────────────────────────────────────────
import json
import os
import subprocess
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
# prometheus_client: official Python client for Prometheus metrics
from prometheus_client import Gauge, CollectorRegistry, push_to_gateway

# ──────────────────────────────────────────────────────────────────────────────
# 2. CONFIGURATION (Edit these as needed)
# ──────────────────────────────────────────────────────────────────────────────
QMS_FILE = 'qms.json'                     # Path to JSON file listing all QMs
PUSHGATEWAY_URL = 'localhost:9091'        # Pushgateway address:port
BASE_JOB = 'mq_stats'                     # Base job name → becomes mq_stats{qmgr="QM1"}
MAX_WORKERS = 15                          # Max parallel threads 

# ──────────────────────────────────────────────────────────────────────────────
# 3. HELPER FUNCTIONS
# ──────────────────────────────────────────────────────────────────────────────

def mq_time_to_epoch_ms(date_str: str, time_str: str) -> int:
    """
    Convert MQ's date + time strings to Unix timestamp in milliseconds.
    Example:
        date_str = "2025-11-01", time_str = "12.34.56"
        → returns 1735684496000 (ms)
    """
    dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H.%M.%S")
    return int(dt.timestamp() * 1000)  # Prometheus expects ms, not seconds


def run_amqsvet(qm_cfg):
    """
    Execute the 'amqsvet' binary to get statistics in JSON format.
    Returns raw JSON string.
    """
    cmd = [
        '/opt/mqm/samp/bin/amqsvet',  # The binary (ensure it's in PATH)
        '-m', qm_cfg['name'],         # Queue manager name
        '-q', 'SYSTEM.ADMIN.STATISTICS.QUEUE',  # Type: queue statistics
        '-o', 'json',                 # Output format
		'-w' 5                        # waits for 5 seconds
    ]
    # Run with timeout to prevent hanging
    return subprocess.check_output(
        cmd, stderr=subprocess.STDOUT, timeout=60
    ).decode('utf-8')


def process_queue_manager(qm_cfg):
    """
    Core logic for ONE queue manager:
      1. Connect via MQSERVER env (Optional. if you are not using channel table)
      2. Run amqsvet → get JSON
      3. Parse timestamps & queue stats
      4. Create Prometheus metrics
      5. Push to Pushgateway with unique job name
    Returns (qm_name, success, message)
    """
    qm_name = qm_cfg['name']
	
	""" Enable the below if you are not using Channel table """
	
    #host = qm_cfg['host']
    #port = qm_cfg['port']
    #channel = qm_cfg['channel']

    # ── Set up MQ client connection via environment variable ──
    #env = os.environ.copy()
    #env['MQSERVER'] = f"{channel}/TCP/{host}({port})"
    
	
	
    # ── Create a fresh Prometheus registry for this QM only ──
    # This ensures metrics from different QMs don't mix
    registry = CollectorRegistry()

    # ── Define Prometheus Gauges (metrics) ──
    enq_vol = Gauge(
        'mq_queue_enqueue_volume_5min',
        'Total messages enqueued in the last 5 minutes',
        ['qmgr', 'queue'],  # Labels: queue manager and queue name
        registry=registry
    )
    deq_vol = Gauge(
        'mq_queue_dequeue_volume_5min',
        'Total messages dequeued in the last 5 minutes',
        ['qmgr', 'queue'],
        registry=registry
    )
    enq_rate = Gauge(
        'mq_queue_enqueue_rate',
        'Enqueue rate (messages per second)',
        ['qmgr', 'queue'],
        registry=registry
    )
    deq_rate = Gauge(
        'mq_queue_dequeue_rate',
        'Dequeue rate (messages per second)',
        ['qmgr', 'queue'],
        registry=registry
    )

    # ── Step 1: Run amqsvet and get JSON ──
    try:
        raw_json = run_amqsvet(qm_cfg)
        data = json.loads(raw_json)
    except subprocess.CalledProcessError as e:
        # amqsvet failed (e.g., connection refused, auth error)
        return qm_name, False, f"amqsvet failed: {e.output.decode().strip()}"
    except json.JSONDecodeError as e:
        return qm_name, False, f"Invalid JSON: {e}"
    except Exception as e:
        return qm_name, False, f"Unexpected error in amqsvet: {e}"

    # ── Step 2: Extract interval timestamps from JSON ──
    try:
        ev = data['eventData']  # Main data block
        start_ts_ms = mq_time_to_epoch_ms(ev['startDate'], ev['startTime'])
        end_ts_ms = mq_time_to_epoch_ms(ev['endDate'], ev['endTime'])
        interval_sec = max((end_ts_ms - start_ts_ms) / 1000.0, 1.0)  # Avoid divide-by-zero
    except Exception as e:
        # Fallback: use current time and assume 5-min interval
        print(f"[{qm_name}] Timestamp parse failed: {e}, using fallback")
        end_ts_ms = int(datetime.utcnow().timestamp() * 1000)
        interval_sec = 300.0  # 5 minutes

    # ── Step 3: Parse per-queue statistics ──
    total_enq = 0
    total_deq = 0
    queue_count = 0

    for q in ev.get('queueStatisticsData', []):
        q_name = q.get('queueName', 'UNKNOWN').strip()

        # Enqueue: sum of non-persistent (index 0) + persistent (index 1)
        puts = q.get('puts', [0, 0])
        put1s = q.get('put1s', [0, 0])
        enq = sum(puts) + sum(put1s)

        # Dequeue: same logic
        gets = q.get('gets', [0, 0])
        get1s = q.get('get1s', [0, 0])
        deq = sum(gets) + sum(get1s)

        # Calculate rates (messages per second)
        rate_enq = enq / interval_sec
        rate_deq = deq / interval_sec

        # ── Set per-queue metrics with EXACT timestamp from MQ ──
        enq_vol.labels(qmgr=qm_name, queue=q_name).set(enq, timestamp=end_ts_ms)
        deq_vol.labels(qmgr=qm_name, queue=q_name).set(deq, timestamp=end_ts_ms)
        enq_rate.labels(qmgr=qm_name, queue=q_name).set(rate_enq, timestamp=end_ts_ms)
        deq_rate.labels(qmgr=qm_name, queue=q_name).set(rate_deq, timestamp=end_ts_ms)

        # Accumulate for QM-level totals
        total_enq += enq
        total_deq += deq
        queue_count += 1

    # ── Step 4: Set queue manager-level totals (queue="total") ──
    total_enq_rate = total_enq / interval_sec
    total_deq_rate = total_deq / interval_sec

    enq_vol.labels(qmgr=qm_name, queue='total').set(total_enq, timestamp=end_ts_ms)
    deq_vol.labels(qmgr=qm_name, queue='total').set(total_deq, timestamp=end_ts_ms)
    enq_rate.labels(qmgr=qm_name, queue='total').set(total_enq_rate, timestamp=end_ts_ms)
    deq_rate.labels(qmgr=qm_name, queue='total').set(total_deq_rate, timestamp=end_ts_ms)

    # ── Step 5: Push to Pushgateway with unique job name ──
    job_name = f"{BASE_JOB}{{qmgr=\"{qm_name}\"}}"  # e.g., mq_stats{qmgr="QM1"}

    try:
        push_to_gateway(
            PUSHGATEWAY_URL,
            job=job_name,
            registry=registry,
            timeout=10
        )
        return qm_name, True, f"{queue_count} queues, enq={total_enq}, deq={total_deq}"
    except Exception as e:
        return qm_name, False, f"Push to gateway failed: {e}"


# ──────────────────────────────────────────────────────────────────────────────
# 4. MAIN: Load QMs and Run in Parallel
# ──────────────────────────────────────────────────────────────────────────────
def main():
    # Load list of queue managers from JSON file
    try:
        with open(QMS_FILE, 'r') as f:
            qms = json.load(f)
    except Exception as e:
        print(f"[FATAL] Cannot read {QMS_FILE}: {e}")
        return

    print(f"Starting parallel collection for {len(qms)} queue managers...")

    # Use ThreadPoolExecutor to process multiple QMs at once
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # Submit all jobs
        future_to_qm = {
            executor.submit(process_queue_manager, qm): qm['name']
            for qm in qms
        }

        # Collect results as they complete
        for future in as_completed(future_to_qm):
            qm_name = future_to_qm[future]
            try:
                name, success, msg = future.result()
                status = "OK" if success else "ERROR"
                print(f"[{status}] {name}: {msg}")
            except Exception as exc:
                print(f"[FATAL] {qm_name} crashed: {exc}")

    print("Collection complete.")


# ──────────────────────────────────────────────────────────────────────────────
# 5. ENTRY POINT
# ──────────────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    main()
