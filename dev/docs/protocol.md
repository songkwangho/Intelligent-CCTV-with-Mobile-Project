# Protocol

## WebSocket Endpoint
- `ws://<host>:<port>/ws`

## Messages

### 1) camera_init
초기 1회 전송.

```json
{
  "type": "camera_init",
  "cameras": {
    "0": {"name":"Camera 1", "bev_x":100, "bev_y":200, "theta":-90, "H":[[...],[...],[...]]},
    "1": {"name":"Camera 2", "bev_x":400, "bev_y":200, "theta":180,  "H":[[...],[...],[...]]}
  }
}

{
  "type": "detected_data",
  "data": {
    "0": {
      "12": {"bev_x": 123.4, "bev_y": 55.6},
      "13": {"bev_x": 130.1, "bev_y": 60.0}
    },
    "1": {
      "7": {"bev_x": 200.1, "bev_y": 90.2}
    }
  }
}

