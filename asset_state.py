"""Decide whether saved scene assets still match the editor's inputs."""
import hashlib
import json

import image_providers


def fingerprint(*values):
    return hashlib.sha256(json.dumps(values, sort_keys=True, default=str).encode()).hexdigest()


def prepare_storyboard(request, generation):
    saved = {scene.get("scene", index + 1): scene
             for index, scene in enumerate(generation.get("storyboard") or [])}
    script = generation.get("script_data") or {}
    provider = image_providers.resolve_provider(request.image_provider)
    result = []
    for index, incoming in enumerate(request.storyboard):
        scene = dict(incoming)
        scene.setdefault("scene", index + 1)
        previous = saved.get(scene["scene"], {})
        speaker = scene.get("speaker") or request.voice
        scene["speaker"] = speaker
        audio_key = fingerprint(scene.get("narration"), speaker, request.speed)
        visual_key = fingerprint(scene.get("visual_prompt"), scene.get("stock_query"),
                                 provider, request.leonardo_model, request.local_image_model,
                                 request.visual_source_mode,
                                 script.get("global_visual_style"), script.get("global_subject_focus"))
        for kind, key, fields in (
            ("audio", audio_key, ("audio_path", "audio_url")),
            ("visual", visual_key, ("image_path", "image_url", "image_id", "clip_path", "clip_url")),
        ):
            # Paths are server-owned. Never consume a filesystem path submitted
            # by a client, and never restore an asset with changed inputs.
            reusable = previous.get(f"{kind}_fingerprint") == key
            for field in fields:
                scene.pop(field, None)
                if reusable and previous.get(field):
                    scene[field] = previous[field]
            scene[f"{kind}_fingerprint"] = key
        result.append(scene)
    return result
