#!/usr/bin/env python3
import os
from pathlib import Path
from anthropic import Anthropic

# Load env
env_file = Path('.env.jira')
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, _, value = line.partition('=')
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and value and key not in os.environ:
            os.environ[key] = value

api_key = os.environ.get('ANTHROPIC_API_KEY')
print('API Key configured:', bool(api_key))

client = Anthropic(api_key=api_key)

# Test 1: Simple call
try:
    msg = client.messages.create(model='claude-opus-4-7', max_tokens=100, messages=[{'role': 'user', 'content': 'Say hi'}])
    print('[OK] Simple API call works')
except Exception as e:
    print(f'[ERROR] Simple API error: {str(e)[:100]}')

# Test 2: Check if response_format is supported
import inspect
sig = inspect.signature(client.messages.create)
print(f'response_format param exists: {"response_format" in sig.parameters}')
print(f'SDK version: 0.103.1')
