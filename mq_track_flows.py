import pymqi
import json
import psycopg2
from typing import Dict, List, Optional
from collections import deque

def fetch_qmgr_details(db_params: Dict) -> Dict[str, Dict]:
    """Fetch Queue Manager details from PostgreSQL."""
    qmgr_details = {}
    try:
        conn = psycopg2.connect(**db_params)
        cursor = conn.cursor()
        cursor.execute("SELECT qmgr_name, host, port, channel, user, password FROM queue_managers")
        for row in cursor.fetchall():
            qmgr_name, host, port, channel, user, password = row
            qmgr_details[qmgr_name] = {
                "host": host,
                "port": port,
                "channel": channel or "SYSTEM.DEF.SVRCONN",
                "user": user,
                "password": password
            }
        cursor.close()
        conn.close()
    except psycopg2.Error as e:
        print(f"Error fetching Queue Manager details from PostgreSQL: {e}")
    return qmgr_details

def connect_to_qmgr(qmgr_name: str, qmgr_details: Dict[str, Dict]) -> Optional[pymqi.QueueManager]:
    """Connect to a Queue Manager using details from qmgr_details."""
    if qmgr_name not in qmgr_details:
        print(f"No connection details found for {qmgr_name}")
        return None
    details = qmgr_details[qmgr_name]
    host = details["host"]
    port = details["port"]
    channel = details["channel"]
    user = details.get("user")
    password = details.get("password")
    try:
        conn_info = f"{host}({port})"
        qmgr = pymqi.QueueManager(None)
        if user and password:
            qmgr.connect_with_options(qmgr_name, conn_info=conn_info, channel=channel, user=user, password=password)
        else:
            qmgr.connect_tcp_client(qmgr_name, conn_info=conn_info, channel=channel)
        return qmgr
    except pymqi.MQMIError as e:
        print(f"Error connecting to {qmgr_name}: {e}")
        return None

def query_queue_details(qmgr: pymqi.QueueManager, queue_name: str) -> Dict:
    """Query details of a queue, including alias base queue."""
    pcf = pymqi.PCFExecute(qmgr)
    try:
        attrs = pcf.MQCMD_INQUIRE_Q([
            pymqi.CMQC.MQCA_Q_NAME,
            pymqi.CMQC.MQIA_Q_TYPE,
            pymqi.CMQC.MQCA_REMOTE_Q_NAME,
            pymqi.CMQC.MQCA_REMOTE_Q_MGR_NAME,
            pymqi.CMQC.MQCA_XMIT_Q_NAME,
            pymqi.CMQC.MQCA_BASE_OBJECT_NAME
        ], {pymqi.CMQC.MQCA_Q_NAME: queue_name})
        return attrs[0] if attrs else {}
    except pymqi.MQMIError as e:
        print(f"Error querying queue {queue_name}: {e}")
        return {}

def query_topic_details(qmgr: pymqi.QueueManager, topic_name: str) -> Dict:
    """Query details of a topic."""
    pcf = pymqi.PCFExecute(qmgr)
    try:
        attrs = pcf.MQCMD_INQUIRE_TOPIC([
            pymqi.CMQC.MQCA_TOPIC_NAME,
            pymqi.CMQC.MQCA_TOPIC_STRING,
            pymqi.CMQC.MQIA_TOPIC_TYPE
        ], {pymqi.CMQC.MQCA_TOPIC_NAME: topic_name})
        return attrs[0] if attrs else {}
    except pymqi.MQMIError as e:
        print(f"Error querying topic {topic_name}: {e}")
        return {}

def query_subscription_details(qmgr: pymqi.QueueManager, topic_name: str = '*') -> List[Dict]:
    """Query subscriptions for a topic."""
    pcf = pymqi.PCFExecute(qmgr)
    try:
        attrs = pcf.MQCMD_INQUIRE_SUBSCRIPTION([
            pymqi.CMQCFC.MQCACF_SUB_NAME,
            pymqi.CMQCFC.MQCACF_TOPIC_NAME,
            pymqi.CMQCFC.MQCACF_DESTINATION,
            pymqi.CMQCFC.MQCACF_DESTINATION_Q_MGR
        ])
        return [sub for sub in attrs if sub.get(pymqi.CMQCFC.MQCACF_TOPIC_NAME, '').strip() == topic_name or topic_name == '*']
    except pymqi.MQMIError as e:
        print(f"Error querying subscriptions: {e}")
        return []

def query_channel_details(qmgr: pymqi.QueueManager, xmit_queue: str = None) -> List[Dict]:
    """Query details of channels associated with a transmission queue."""
    pcf = pymqi.PCFExecute(qmgr)
    try:
        channels = pcf.MQCMD_INQUIRE_CHANNEL([
            pymqi.CMQCFC.MQCACH_CHANNEL_NAME,
            pymqi.CMQCFC.MQIA_CHANNEL_TYPE,
            pymqi.CMQCFC.MQCACH_XMIT_Q_NAME,
            pymqi.CMQCFC.MQCACH_CONNECTION_NAME
        ])
        if xmit_queue:
            return [ch for ch in channels if ch.get(pymqi.CMQCFC.MQCACH_XMIT_Q_NAME, '').strip() == xmit_queue]
        return channels
    except pymqi.MQMIError as e:
        print(f"Error querying channels: {e}")
        return []

def trace_message_flow(qmgr_name: str, object_name: str, object_type: str, db_params: Dict) -> Dict:
    """Trace the end-to-end message flow for a queue or topic iteratively."""
    # Fetch Queue Manager details from PostgreSQL
    qmgr_details = fetch_qmgr_details(db_params)
    
    flow_details = {
        "starting_queue_manager": qmgr_name,
        "object_name": object_name,
        "object_type": object_type,
        "flow_path": []
    }
    
    # Use a queue to manage hops iteratively
    hop_queue = deque([(qmgr_name, object_name, object_type)])
    visited = set()  # Track visited Queue Managers to avoid loops
    
    while hop_queue:
        current_qmgr_name, current_obj_name, current_obj_type = hop_queue.popleft()
        
        if current_qmgr_name in visited:
            flow_details["flow_path"].append({"note": f"Loop detected at {current_qmgr_name}, stopping trace"})
            continue
        visited.add(current_qmgr_name)
        
        # Connect to the current Queue Manager
        qmgr = connect_to_qmgr(current_qmgr_name, qmgr_details)
        if not qmgr:
            flow_details["flow_path"].append({"error": f"Failed to connect to {current_qmgr_name}"})
            continue

        obj_info = {
            "queue_manager": current_qmgr_name,
            "object_name": current_obj_name,
            "object_type": current_obj_type,
            "details": {}
        }

        if current_obj_type == "queue":
            # Query queue details
            queue_details = query_queue_details(qmgr, current_obj_name)
            if not queue_details:
                obj_info["error"] = f"Queue {current_obj_name} not found on {current_qmgr_name}"
                flow_details["flow_path"].append(obj_info)
                qmgr.disconnect()
                continue

            queue_type = queue_details.get(pymqi.CMQC.MQIA_Q_TYPE)
            if queue_type == pymqi.CMQC.MQQT_ALIAS:
                obj_info["details"]["type"] = "Alias"
                base_object_name = queue_details.get(pymqi.CMQC.MQCA_BASE_OBJECT_NAME, "").strip()
                obj_info["details"]["base_object_name"] = base_object_name
                if base_object_name:
                    # Determine if base object is a queue or topic
                    base_queue_details = query_queue_details(qmgr, base_object_name)
                    if base_queue_details:
                        base_queue_type = base_queue_details.get(pymqi.CMQC.MQIA_Q_TYPE)
                        obj_info["details"]["base_object_type"] = "queue"
                        if base_queue_type == pymqi.CMQC.MQQT_LOCAL:
                            obj_info["details"]["base_queue_type"] = "Local"
                            xmit_queue = base_queue_details.get(pymqi.CMQC.MQCA_XMIT_Q_NAME, "").strip()
                            if xmit_queue:
                                obj_info["details"]["transmission_queue"] = xmit_queue
                                channels = query_channel_details(qmgr, xmit_queue)
                                if channels:
                                    obj_info["details"]["channel"] = {
                                        "name": channels[0][pymqi.CMQCFC.MQCACH_CHANNEL_NAME].strip(),
                                        "type": channels[0][pymqi.CMQCFC.MQIA_CHANNEL_TYPE],
                                        "connection_name": channels[0][pymqi.CMQCFC.MQCACH_CONNECTION_NAME].strip()
                                    }
                        elif base_queue_type == pymqi.CMQC.MQQT_REMOTE:
                            obj_info["details"]["base_queue_type"] = "Remote"
                            remote_qmgr = base_queue_details.get(pymqi.CMQC.MQCA_REMOTE_Q_MGR_NAME, "").strip()
                            remote_queue = base_queue_details.get(pymqi.CMQC.MQCA_REMOTE_Q_NAME, "").strip()
                            xmit_queue = base_queue_details.get(pymqi.CMQC.MQCA_XMIT_Q_NAME, "").strip()
                            obj_info["details"]["remote_queue_manager"] = remote_qmgr
                            obj_info["details"]["remote_queue"] = remote_queue
                            if xmit_queue:
                                obj_info["details"]["transmission_queue"] = xmit_queue
                                channels = query_channel_details(qmgr, xmit_queue)
                                if channels:
                                    obj_info["details"]["channel"] = {
                                        "name": channels[0][pymqi.CMQCFC.MQCACH_CHANNEL_NAME].strip(),
                                        "type": channels[0][pymqi.CMQCFC.MQIA_CHANNEL_TYPE],
                                        "connection_name": channels[0][pymqi.CMQCFC.MQCACH_CONNECTION_NAME].strip()
                                    }
                            if remote_qmgr and remote_queue:
                                hop_queue.append((remote_qmgr, remote_queue, "queue"))
                                obj_info["details"]["next_hop"] = f"{remote_queue} on {remote_qmgr}"
                        hop_queue.append((current_qmgr_name, base_object_name, "queue"))
                    else:
                        # Check if base object is a topic
                        base_topic_details = query_topic_details(qmgr, base_object_name)
                        if base_topic_details:
                            obj_info["details"]["base_object_type"] = "topic"
                            hop_queue.append((current_qmgr_name, base_object_name, "topic"))
            elif queue_type == pymqi.CMQC.MQQT_LOCAL:
                obj_info["details"]["type"] = "Local"
                xmit_queue = queue_details.get(pymqi.CMQC.MQCA_XMIT_Q_NAME, "").strip()
                if xmit_queue:
                    obj_info["details"]["transmission_queue"] = xmit_queue
                    channels = query_channel_details(qmgr, xmit_queue)
                    if channels:
                        obj_info["details"]["channel"] = {
                            "name": channels[0][pymqi.CMQCFC.MQCACH_CHANNEL_NAME].strip(),
                            "type": channels[0][pymqi.CMQCFC.MQIA_CHANNEL_TYPE],
                            "connection_name": channels[0][pymqi.CMQCFC.MQCACH_CONNECTION_NAME].strip()
                        }
            elif queue_type == pymqi.CMQC.MQQT_REMOTE:
                obj_info["details"]["type"] = "Remote"
                remote_qmgr = queue_details.get(pymqi.CMQC.MQCA_REMOTE_Q_MGR_NAME, "").strip()
                remote_queue = queue_details.get(pymqi.CMQC.MQCA_REMOTE_Q_NAME, "").strip()
                xmit_queue = queue_details.get(pymqi.CMQC.MQCA_XMIT_Q_NAME, "").strip()
                obj_info["details"]["remote_queue_manager"] = remote_qmgr
                obj_info["details"]["remote_queue"] = remote_queue
                if xmit_queue:
                    obj_info["details"]["transmission_queue"] = xmit_queue
                    channels = query_channel_details(qmgr, xmit_queue)
                    if channels:
                        obj_info["details"]["channel"] = {
                            "name": channels[0][pymqi.CMQCFC.MQCACH_CHANNEL_NAME].strip(),
                            "type": channels[0][pymqi.CMQCFC.MQIA_CHANNEL_TYPE],
                            "connection_name": channels[0][pymqi.CMQCFC.MQCACH_CONNECTION_NAME].strip()
                        }
                if remote_qmgr and remote_queue:
                    hop_queue.append((remote_qmgr, remote_queue, "queue"))
                    obj_info["details"]["next_hop"] = f"{remote_queue} on {remote_qmgr}"
            else:
                obj_info["details"]["type"] = "Unsupported queue type"

        elif current_obj_type == "topic":
            # Query topic details
            topic_details = query_topic_details(qmgr, current_obj_name)
            if not topic_details:
                obj_info["error"] = f"Topic {current_obj_name} not found on {current_qmgr_name}"
                flow_details["flow_path"].append(obj_info)
                qmgr.disconnect()
                continue

            obj_info["details"]["type"] = "Topic"
            obj_info["details"]["topic_string"] = topic_details.get(pymqi.CMQC.MQCA_TOPIC_STRING, "").strip()
            
            # Query subscriptions for this topic
            subscriptions = query_subscription_details(qmgr, current_obj_name)
            if subscriptions:
                obj_info["details"]["subscriptions"] = [
                    {
                        "name": sub[pymqi.CMQCFC.MQCACF_SUB_NAME].strip(),
                        "destination": sub[pymqi.CMQCFC.MQCACF_DESTINATION].strip(),
                        "destination_queue_manager": sub[pymqi.CMQCFC.MQCACF_DESTINATION_Q_MGR].strip() or current_qmgr_name
                    } for sub in subscriptions
                ]
                for sub in subscriptions:
                    dest_queue = sub[pymqi.CMQCFC.MQCACF_DESTINATION].strip()
                    dest_qmgr = sub[pymqi.CMQCFC.MQCACF_DESTINATION_Q_MGR].strip() or current_qmgr_name
                    if dest_queue:
                        hop_queue.append((dest_qmgr, dest_queue, "queue"))
                        obj_info["details"].setdefault("next_hops", []).append(f"{dest_queue} on {dest_qmgr}")

        flow_details["flow_path"].append(obj_info)
        qmgr.disconnect()

    return flow_details

def main():
    # PostgreSQL connection parameters
    db_params = {
        "dbname": "your_database",
        "user": "your_username",
        "password": "your_password",
        "host": "localhost",
        "port": "5432"
    }

    # MQ parameters
    qmgr_name = "QM1" # Queue Manager Name
    object_name = "ALIAS.QUEUE"  # Example alias queue
    object_type = "queue"

    flow_details = trace_message_flow(qmgr_name, object_name, object_type, db_params)
    print(json.dumps(flow_details, indent=2))

if __name__ == "__main__":
    main()
