# Bridge Protocol and Build Guide

This document defines the bridge message protocol standard and provides a quickstart for the generic pipeline bridge.

## 1. Scope and phases

- Phase 1 (current): unify SAM3 + FlowPose message protocol.
- Phase 2 (future): unify additional services (Siglip, Marvin, Fast-FoundationStereo, etc.).

## 2. Message categories (6 types)

This project recognizes six message categories. Each category defines its core fields.

1. RGB
   - Primary producer: Fast-FoundationStereoDocker
   - Fields:
     - rgb_image (base64, jpg preferred)
     - image_encoding.rgb_image (optional)

2. Depth
   - Primary producer: Fast-FoundationStereoDocker
   - Fields:
     - depth_image (base64, png preferred)
     - image_encoding.depth_image (optional)

3. Mask
   - Primary producer: Sam3Docker
   - Fields:
     - combined_mask_b64 (base64, png)
     - obj_ids (list of [track_id, instance_id])
     - class_names (list of labels, optional)
     - instance_names (list of labels, optional)
     - detections (optional detail list)

4. Pose
   - Primary producer: FlowPoseDocker
   - Fields:
     - objects (list of poses)
     - request_id
     - elapsed_sec

5. Action
   - Primary producer: MarvinDocker
   - Fields:
     - action or actions
     - status
     - request_id

6. Status
   - Producers: all services
   - Fields:
     - status (ok/error)
     - message (error detail)
     - elapsed_sec
     - request_id

## 3. Unified request/response schema (Phase 1)

### 3.1 SAM3 request

- request_id (string)
- rgb_image (base64 jpg)
- prompts (list of strings)
- return_masks (bool)
- clear_previous (bool)

### 3.2 SAM3 response

- status (ok/error)
- request_id
- elapsed_sec
- detections (list of {id, label, score, bbox, mask_png_b64})
- combined_mask_b64 (base64 png, may be empty if no detections)
- obj_ids (list of [track_id, instance_id])
- class_names (list of labels)
- instance_names (list of labels)

### 3.3 FlowPose request

- request_id
- rgb_image (base64 jpg)
- depth_image (base64 png)
- combined_mask_b64 (base64 png)
- obj_ids (list)
- class_names (optional)
- instance_names (optional)

### 3.4 FlowPose response

- status (ok/error)
- request_id
- objects (list)
- elapsed_sec

## 4. Generic bridge pipeline usage

Example config (Sam3 + FlowPose):

```yaml
bridge:
  type: custom_pipeline
  source_mode: zmq_source
  zmq_source_addr: tcp://127.0.0.1:4444
  prompts:
    - cup
    - red box
  pipeline_outputs:
    - objects
    - rgb_image
    - depth_image
    - combined_mask_b64
  pipeline:
    - name: sam3
      kind: generic
      endpoint: tcp://127.0.0.1:5562
      timeout_ms: 5000
      role: required
      inputs:
        - rgb_image
        - prompts
      request_map:
        request_id: $request_id
        rgb_image: $rgb_image
        prompts: $prompts
        return_masks:
          value: true
        clear_previous:
          value: true
      response_map:
        combined_mask_b64: combined_mask_b64
        obj_ids: obj_ids
        class_names: class_names
        instance_names: instance_names

    - name: flowpose
      kind: generic
      endpoint: tcp://127.0.0.1:6667
      depends_on:
        - sam3
      role: required
      inputs:
        - rgb_image
        - depth_image
        - combined_mask_b64
        - obj_ids
      request_map:
        request_id: $request_id
        rgb_image: $rgb_image
        depth_image: $depth_image
        combined_mask: $combined_mask_b64
        obj_ids: $obj_ids
        class_names: $class_names
        instance_names: $instance_names
      response_map:
        objects: objects
```

Start the bridge:

```bash
PYTHONPATH=src python3 -m fusion_docker serve-bridge --config configs/bridge.custom.yaml
```

## 5. Notes and migration

- In Phase 1, Fast-FoundationStereoDocker remains the RGB/Depth source.
- The bridge is now fully generic for Sam3 + FlowPose once servers emit the unified fields.
- Future services should align to the same core fields to avoid per-service adapters.
