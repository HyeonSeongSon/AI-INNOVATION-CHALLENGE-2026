"""
JSON 파일에서 페르소나 데이터를 읽어서 PostgreSQL에 삽입
"""

import sys
import os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "backend"))

import json
from app.core.database import get_db
from app.core.models import Persona
from sqlalchemy.exc import IntegrityError


def insert_personas():
    """data 폴더의 모든 persona_*.json 파일을 읽어서 DB에 삽입"""

    # data 폴더 경로
    data_dir = Path(__file__).parent.parent / "data"
    persona_files = list(data_dir.glob("persona_*.json"))

    if not persona_files:
        print("=" * 60)
        print("No persona files found!")
        print("=" * 60)
        print(f"Looking in: {data_dir}")
        print("Expected pattern: persona_*.json")
        return

    print("=" * 60)
    print("Insert Personas to PostgreSQL")
    print("=" * 60)
    print(f"Found {len(persona_files)} persona file(s)")
    print()

    # 페르소나 데이터 로드
    personas_data = []
    for file_path in persona_files:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            personas_data.append(data)
            print(f"  - Loaded: {file_path.name}")

    print()
    print(f"Total personas to insert: {len(personas_data)}")
    print()

    # 데이터베이스에 삽입
    success_count = 0
    skip_count = 0
    error_count = 0

    with next(get_db()) as db:
        for data in personas_data:
            try:
                persona = Persona(
                    persona_id=data.get('persona_id'),
                    name=data.get('name'),
                    gender=data.get('gender'),
                    age=data.get('age'),
                    occupation=data.get('occupation'),
                    skin_type=data.get('skin_type', []),
                    concerns=data.get('concerns', data.get('skin_concerns', [])),
                    personal_color=data.get('personal_color'),
                    shade_number=data.get('shade_number'),
                    preferred_colors=data.get('preferred_colors', []),
                    preferred_ingredients=data.get('preferred_ingredients', []),
                    avoided_ingredients=data.get('avoided_ingredients', []),
                    preferred_scents=data.get('preferred_scents', []),
                    lifestyle_values=data.get('lifestyle_values', data.get('values', [])),
                    skincare_routine=data.get('skincare_routine', []),
                    main_environment=data.get('main_environment', []),
                    preferred_texture=data.get('preferred_texture', []),
                    hair_type=data.get('hair_type', []),
                    beauty_interests=data.get('beauty_interests', []),
                    pets=data.get('pets', []),
                    avg_sleep_hours=data.get('avg_sleep_hours'),
                    stress_level=data.get('stress_level'),
                    daily_screen_hours=data.get('daily_screen_hours', data.get('digital_device_usage_time')),
                    shopping_style=data.get('shopping_style', []),
                    purchase_decision_factors=data.get('purchase_decision_factors', []),
                    price_sensitivity=data.get('price_sensitivity'),
                    preferred_brands=data.get('preferred_brands', []),
                    avoided_brands=data.get('avoided_brands', [])
                )

                db.add(persona)
                db.commit()
                success_count += 1
                print(f"  [OK] Inserted: {persona.persona_id} - {persona.name}")

            except IntegrityError:
                db.rollback()
                skip_count += 1
                print(f"  [SKIP] Already exists: {data.get('persona_id')}")
            except Exception as e:
                db.rollback()
                error_count += 1
                print(f"  [ERROR] {data.get('persona_id')}: {e}")

    print()
    print("=" * 60)
    print("Insert Complete!")
    print("=" * 60)
    print(f"Success: {success_count}")
    print(f"Skipped (duplicate): {skip_count}")
    print(f"Errors: {error_count}")
    print(f"Total: {len(personas_data)}")
    print("=" * 60)


if __name__ == "__main__":
    insert_personas()
