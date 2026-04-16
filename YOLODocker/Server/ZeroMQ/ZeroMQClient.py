import base64
import json
import uuid
import zmq


def encode_file_to_base64(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def main():
    rgb_path = "/home/yang/Desktop/DockerModel/FlowPoseDocker/FlowPose/test/rgb/000013.png"

    request_data = {
        "request_id": str(uuid.uuid4()),
        "rgb_image": encode_file_to_base64(rgb_path),
        "conf": 0.8,
        "tracker": "bytetrack.yaml",
        "persist": True,
        "return_masks": True,
    }

    context = zmq.Context()
    socket = context.socket(zmq.REQ)
    socket.connect("tcp://127.0.0.1:5555")

    print("Sending request...")
    socket.send_json(request_data)

    response = socket.recv_json()

    # 打印返回结果
    print(json.dumps(response, indent=2, ensure_ascii=False))

    # 保存 JSON
    output_file = "response.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(response, f, indent=2, ensure_ascii=False)

    print(f"Response saved to {output_file}")


if __name__ == "__main__":
    main()