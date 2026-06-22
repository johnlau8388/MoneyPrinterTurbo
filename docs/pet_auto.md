# Pet Auto Daily Video

This feature adds a small automation layer for recurring pet short videos without changing MoneyPrinterTurbo's core rendering pipeline.

## What it does

- Stores pet profiles in `storage/pet_auto/pet_auto.sqlite3`.
- Uses uploaded local materials from `storage/local_videos`.
- Generates a daily topic and narration for each active pet profile.
- Submits a normal MoneyPrinterTurbo video task with `video_source = local`.
- Tracks the generated task in a pet content plan.
- Optionally starts an in-process daily scheduler when the API server starts.

## Configuration

Add these keys under `[app]` in `config.toml` when you want automatic daily generation:

```toml
pet_auto_enabled = true
pet_auto_daily_time = "09:00"
```

`pet_auto_daily_time` uses the server's local time in `HH:MM` format. Each profile can override it with its own `daily_time`.

## Basic usage

### 1. Upload pet images

Use the existing endpoint:

```bash
curl -F "file=@dog_001.jpg" http://127.0.0.1:8080/api/v1/video_materials
curl -F "file=@dog_002.jpg" http://127.0.0.1:8080/api/v1/video_materials
```

The returned `file` values should be used in the profile's `image_files`.

### 2. Create a pet profile

```bash
curl -X POST http://127.0.0.1:8080/api/v1/pet/profiles \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Milo",
    "species": "dog",
    "description": "A playful golden retriever who looks innocent after making trouble.",
    "image_files": ["dog_001.jpg", "dog_002.jpg"],
    "active": true,
    "language": "zh-CN",
    "daily_time": "09:00",
    "topic_templates": [
      "{name}今天假装听懂了主人的话",
      "{name}用一个眼神骗到了零食",
      "{name}为什么总在主人忙的时候撒娇"
    ],
    "style_prompt": "轻松、拟人、适合宠物账号日更",
    "video_params": {
      "voice_name": "zh-CN-XiaoxiaoNeural-Female",
      "video_clip_duration": 5,
      "bgm_type": "random"
    }
  }'
```

### 3. Generate one video manually

```bash
curl -X POST http://127.0.0.1:8080/api/v1/pet/profiles/<pet_id>/generate \
  -H "Content-Type: application/json" \
  -d '{"topic":"Milo今天偷看主人吃饭", "force": false}'
```

The response includes a `task_id`. Query the normal task endpoint for progress:

```bash
curl http://127.0.0.1:8080/api/v1/tasks/<task_id>
```

### 4. Sync a plan after the video task completes

```bash
curl -X POST http://127.0.0.1:8080/api/v1/pet/plans/<plan_id>/sync
```

## API summary

- `POST /api/v1/pet/profiles`
- `GET /api/v1/pet/profiles`
- `GET /api/v1/pet/profiles/{pet_id}`
- `PUT /api/v1/pet/profiles/{pet_id}`
- `DELETE /api/v1/pet/profiles/{pet_id}`
- `POST /api/v1/pet/profiles/{pet_id}/generate`
- `GET /api/v1/pet/plans`
- `GET /api/v1/pet/plans/{plan_id}`
- `POST /api/v1/pet/plans/{plan_id}/sync`
- `GET /api/v1/pet/scheduler`
- `POST /api/v1/pet/scheduler/run_today`
- `POST /api/v1/pet/scheduler/run_due_once`

## Notes

This implementation uses uploaded images or videos as local materials. It does not yet generate new image-to-video scenes from a pet reference photo. For a more advanced virtual pet IP workflow, add an image-to-video provider before the local-material video task is submitted.
