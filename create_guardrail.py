#!/usr/bin/env python3
"""
Create a Bedrock Guardrail with basic content filtering settings.
Saves the Guardrail ID to .env file for use by telegram_bot.py.
"""

import os
import sys
from pathlib import Path

import boto3

try:
    from dotenv import load_dotenv, set_key
    load_dotenv()
except ImportError:
    print("Error: python-dotenv not installed. Run: uv add python-dotenv")
    sys.exit(1)


def create_guardrail(region):
    """Create a Bedrock Guardrail with basic content filtering."""
    bedrock = boto3.client('bedrock', region_name=region)
    
    try:
        response = bedrock.create_guardrail(
            name='TelegramBotGuardrail',
            description='Content filtering for Telegram bot inputs',
            contentPolicyConfig={
                'filtersConfig': [
                    {'type': 'SEXUAL', 'inputStrength': 'HIGH', 'outputStrength': 'HIGH'},
                    {'type': 'VIOLENCE', 'inputStrength': 'HIGH', 'outputStrength': 'HIGH'},
                    {'type': 'HATE', 'inputStrength': 'HIGH', 'outputStrength': 'HIGH'},
                    {'type': 'INSULTS', 'inputStrength': 'MEDIUM', 'outputStrength': 'MEDIUM'},
                    {'type': 'MISCONDUCT', 'inputStrength': 'MEDIUM', 'outputStrength': 'MEDIUM'},
                    {'type': 'PROMPT_ATTACK', 'inputStrength': 'HIGH', 'outputStrength': 'NONE'}
                ]
            },
            blockedInputMessaging='Your input was blocked by content filtering.',
            blockedOutputsMessaging='The response was blocked by content filtering.'
        )
        
        guardrail_id = response['guardrailId']
        version = response['version']
        
        print(f"✅ Guardrail created successfully!")
        print(f"   Guardrail ID: {guardrail_id}")
        print(f"   Version: {version}")
        
        return guardrail_id, version
        
    except Exception as e:
        print(f"❌ Failed to create guardrail: {e}")
        sys.exit(1)


def save_to_env(guardrail_id, version):
    """Save guardrail ID to .env file."""
    env_file = Path(__file__).parent / '.env'
    
    if not env_file.exists():
        print(f"\n⚠️  .env file not found. Creating new file...")
        env_file.touch()
    
    set_key(env_file, 'BEDROCK_GUARDRAIL_ID', guardrail_id)
    set_key(env_file, 'BEDROCK_GUARDRAIL_VERSION', version)
    
    print(f"\n✅ Saved to {env_file}")
    print(f"   BEDROCK_GUARDRAIL_ID={guardrail_id}")
    print(f"   BEDROCK_GUARDRAIL_VERSION={version}")


def main():
    region = os.environ.get('AWS_REGION', 'us-west-2')
    
    print(f"Creating Bedrock Guardrail in {region}...")
    print("This will create a guardrail with the following filters:")
    print("  - Sexual content: HIGH")
    print("  - Violence: HIGH")
    print("  - Hate speech: HIGH")
    print("  - Insults: MEDIUM")
    print("  - Misconduct: MEDIUM")
    print("  - Prompt attacks: HIGH")
    print()
    
    guardrail_id, version = create_guardrail(region)
    save_to_env(guardrail_id, version)
    
    print("\n🎉 Setup complete! Restart telegram_bot.py to use the guardrail.")


if __name__ == '__main__':
    main()
