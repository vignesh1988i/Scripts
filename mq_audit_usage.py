#!/usr/bin/env python3
"""
MQ Daily Audit - more Queue Managers
IBM MQ 9.3.x | PostgreSQL | Restart-Safe
"""

import subprocess
import os
import re
import json
import logging
from datetime import datetime
import psycopg2
from psycopg2.extras import execute_values
from concurrent.futures import ThreadPoolExecutor, as_completed

# ============================= CONFIG =============================
DB_CONFIG = {
    "host":     os.getenv("DB_HOST", "localhost"),
    "port":     int(os.getenv("DB_PORT", "5432")),
    "dbname":   os.getenv("DB_NAME", "mq_audit"),
    "user":     os.getenv("DB_USER", "mquser"),
    "password": os.getenv("DB_PASS", "mqpass")
}

QM_CONFIG_FILE = os.getenv("QM_CONFIG_FILE", "qm_config.json")
MAX_WORKERS = int(os.getenv("MAX_WORKERS", "10"))

# Logging
logging.basicConfig(
    filename='mq_audit.log',
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | [%(qm_name)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# ============================= MQSC CONTENT =============================
def get_mqsc_content():
    return """
DEFINE PROCESS(MQSC.DEFAULT.BROWSE.PROC) PROCESSDESC('') APPLTYPE(UNIX) REPLACE
DISPLAY QSTATUS(*) TYPE(QUEUE) LGETDATE LGETTIME LPUTDATE LPUTTIME
EXIT
"""

# ============================= RUNMQSC =============================
def run_mqsc_client(qm_name, host, port, channel):
    logging.info("Connecting...", extra={'qm_name': qm_name})
    os.environ['MQSERVER'] = f"{channel}/TCP/{host}({port})"
    cmd = ['runmqsc', '-c', qm_name]

    try:
        process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        stdout, stderr = process.communicate(input=get_mqsc_content(), timeout=30)

        if process.returncode != 0:
            logging.error(f"runmqsc failed: {stderr.strip()}", extra={'qm_name': qm_name})
            return None

        logging.info("runmqsc completed", extra={'qm_name': qm_name})
        return stdout

    except Exception as e:
        logging.error(f"Exception: {e}", extra={'qm_name': qm_name})
        return None
    finally:
        os.environ.pop('MQSERVER', None)

# ============================= PARSE OUTPUT =============================
def parse_qstatus_output(output, qm_name):
    queues = {}
    lines = output.splitlines()
    current_queue = None

    for line in lines:
        line = line.strip()

        if line.startswith('AMQ8450I') and 'QUEUE(' in line:
            match = re.search(r'QUEUE\(([^)]+)\)', line)
            if match:
                current_queue = match.group(1).strip()
                queues[current_queue] = {}

        elif current_queue:
            for attr in ['LGETDATE', 'LGETTIME', 'LPUTDATE', 'LPUTTIME']:
                if attr + '(' in line:
                    match = re.search(rf'{attr}\(([^)]*)\)', line)
                    if match:
                        val = match.group(1).strip()
                        key = {
                            'LGETDATE': 'lget_date',
                            'LGETTIME': 'lget_time',
                            'LPUTDATE': 'lput_date',
                            'LPUTTIME': 'lput_time'
                        }[attr]
                        queues[current_queue][key] = val if val else None

    logging.info(f"Parsed {len(queues)} queues", extra={'qm_name': qm_name})
    return queues

# ============================= DATABASE UPSERT (RESTART-SAFE) =============================
def upsert_to_db(qm_name, queue_stats):
    if not queue_stats:
        logging.warning("No stats to insert", extra={'qm_name': qm_name})
        return

    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        audit_ts = datetime.now()
        data = []

        for qname, stats in queue_stats.items():
            lget_date = stats.get('lget_date')
            lget_time = stats.get('lget_time')
            lput_date = stats.get('lput_date')
            lput_time = stats.get('lput_time')

            # Skip if ALL 4 timestamps are blank (QM restart)
            if not any([lget_date, lget_time, lput_date, lput_time]):
                logging.info(f"Skipping {qname}: all timestamps blank (QM restart?)",
                            extra={'qm_name': qm_name})
                continue

            data.append((
                qm_name,
                qname,
                lget_date or None,
                lget_time or None,
                lput_date or None,
                lput_time or None,
                audit_ts
            ))

        if not data:
            logging.info("No valid data to upsert (all queues blank)", extra={'qm_name': qm_name})
            print(f"Skipped: [{qm_name}] – all queues blank (likely restart)")
            return

        with conn.cursor() as cur:
            sql = """
                INSERT INTO queue_audit
                (queue_manager, queue_name, last_get_date, last_get_time,
                 last_put_date, last_put_time, audit_date)
                VALUES %s
                ON CONFLICT (queue_manager, queue_name, audit_day)
                DO UPDATE SET
                    last_get_date = COALESCE(EXCLUDED.last_get_date, queue_audit.last_get_date),
                    last_get_time = COALESCE(EXCLUDED.last_get_time, queue_audit.last_get_time),
                    last_put_date = COALESCE(EXCLUDED.last_put_date, queue_audit.last_put_date),
                    last_put_time = COALESCE(EXCLUDED.last_put_time, queue_audit.last_put_time),
                    audit_date    = EXCLUDED.audit_date;
            """
            execute_values(cur, sql, data)
            conn.commit()

        logging.info(f"Upserted {len(data)} queues (blanks preserved)", extra={'qm_name': qm_name})
        print(f"Success: [{qm_name}] → {len(data)} queues updated")

    except Exception as e:
        logging.error(f"DB error: {e}", extra={'qm_name': qm_name})
        print(f"Failed: [{qm_name}] DB insert failed")
    finally:
        if conn:
            conn.close()

# ============================= PROCESS ONE QM =============================
def process_queue_manager(qm_config):
    qm_name = qm_config['qm_name']
    try:
        output = run_mqsc_client(
            qm_name=qm_name,
            host=qm_config['host'],
            port=qm_config['port'],
            channel=qm_config['channel']
        )
        if not output:
            return qm_name, 0, "runmqsc failed"

        stats = parse_qstatus_output(output, qm_name)
        if stats:
            upsert_to_db(qm_name, stats)
            return qm_name, len(stats), None
        else:
            return qm_name, 0, "No queues parsed"

    except Exception as e:
        logging.error(f"Unexpected error: {e}", extra={'qm_name': qm_name})
        return qm_name, 0, str(e)

# ============================= MAIN =============================
def main():
    print(f"MQ Audit Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logging.info("=== MQ AUDIT RUN START ===")

    try:
        with open(QM_CONFIG_FILE, 'r') as f:
            qm_list = json.load(f)
    except Exception as e:
        print(f"Failed to load {QM_CONFIG_FILE}: {e}")
        return

    print(f"Loaded {len(qm_list)} queue managers")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(process_queue_manager, qm): qm['qm_name']
            for qm in qm_list
        }

        for future in as_completed(futures):
            qm_name = futures[future]
            try:
                qm, count, error = future.result()
                if error:
                    print(f"Failed: [{qm}] {error}")
                else:
                    print(f"Success: [{qm}] {count} queues")
            except Exception as e:
                print(f"Failed: [{qm_name}] {e}")

    print(f"MQ Audit Finished: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logging.info("=== MQ AUDIT RUN END ===\n")

if __name__ == "__main__":
    main()
