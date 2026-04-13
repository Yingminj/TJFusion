from __future__ import annotations

import json

import zmq


def main() -> None:
    context = zmq.Context.instance()
    socket = context.socket(zmq.SUB)
    socket.connect("tcp://127.0.0.1:6010")
    socket.setsockopt_string(zmq.SUBSCRIBE, "fusion.command")

    print("listening on tcp://127.0.0.1:6010 topic=fusion.command")
    try:
        while True:
            raw_message = socket.recv_string()
            topic, _, payload = raw_message.partition(" ")
            print(f"\n[{topic}]")
            print(json.dumps(json.loads(payload), ensure_ascii=False, indent=2))
    except KeyboardInterrupt:
        pass
    finally:
        socket.close(0)


if __name__ == "__main__":
    main()

