Script usage:

python mq_track_flow.py

Output 1: if you provide an alias queue

{
  "starting_queue_manager": "QM1",
  "object_name": "ALIAS.QUEUE",
  "object_type": "queue",
  "flow_path": [
    {
      "queue_manager": "QM1",
      "object_name": "ALIAS.QUEUE",
      "object_type": "queue",
      "details": {
        "type": "Alias",
        "base_object_name": "REMOTE.QUEUE",
        "base_object_type": "queue",
        "base_queue_type": "Remote",
        "remote_queue_manager": "QM2",
        "remote_queue": "TARGET.QUEUE",
        "transmission_queue": "QM2.XMITQ",
        "channel": {
          "name": "QM1.TO.QM2",
          "type": 1,
          "connection_name": "192.168.1.20(1414)"
        },
        "next_hop": "TARGET.QUEUE on QM2"
      }
    },
    {
      "queue_manager": "QM2",
      "object_name": "TARGET.QUEUE",
      "object_type": "queue",
      "details": {
        "type": "Local"
      }
    }
  ]
}




Output 2: If you provide a Topic

{
  "starting_queue_manager": "QM1",
  "object_name": "ALIAS.QUEUE",
  "object_type": "queue",
  "flow_path": [
    {
      "queue_manager": "QM1",
      "object_name": "ALIAS.QUEUE",
      "object_type": "queue",
      "details": {
        "type": "Alias",
        "base_object_name": "MY.TOPIC",
        "base_object_type": "topic"
      }
    },
    {
      "queue_manager": "QM1",
      "object_name": "MY.TOPIC",
      "object_type": "topic",
      "details": {
        "type": "Topic",
        "topic_string": "/app/topic",
        "subscriptions": [
          {
            "name": "SUB1",
            "destination": "SUB.QUEUE",
            "destination_queue_manager": "QM1"
          }
        ],
        "next_hops": [
          "SUB.QUEUE on QM1"
        ]
      }
    },
    {
      "queue_manager": "QM1",
      "object_name": "SUB.QUEUE",
      "object_type": "queue",
      "details": {
        "type": "Local"
      }
    }
  ]
}
