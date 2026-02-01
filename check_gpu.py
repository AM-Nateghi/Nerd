#!/usr/bin/env python3
"""Check GPU and CUDA availability"""

import torch
import sys

print("=" * 60)
print("🔍 GPU/CUDA Diagnostics")
print("=" * 60)

# PyTorch version
print(f"\n📦 PyTorch version: {torch.__version__}")

# CUDA availability
print(f"✅ CUDA available: {torch.cuda.is_available()}")
print(f"📊 CUDA version (PyTorch): {torch.version.cuda}")

# GPU devices
if torch.cuda.is_available():
    print(f"\n🎮 Number of GPUs: {torch.cuda.device_count()}")
    for i in range(torch.cuda.device_count()):
        props = torch.cuda.get_device_properties(i)
        print(f"\n  GPU {i}: {props.name}")
        print(f"    Total Memory: {props.total_memory / 1e9:.2f} GB")
        print(f"    Compute Capability: {props.major}.{props.minor}")
else:
    print("\n❌ No CUDA devices found!")
    print("\n🔧 Possible solutions:")
    print("   1. Check NVIDIA drivers: nvidia-smi")
    print("   2. Install CUDA toolkit")
    print("   3. Reinstall PyTorch with CUDA support:")
    print("      pip uninstall torch -y")
    print(
        "      pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121"
    )

# Test tensor on GPU
print("\n" + "=" * 60)
print("🧪 Testing GPU tensor operation...")
print("=" * 60)

try:
    x = torch.randn(1000, 1000)
    if torch.cuda.is_available():
        x = x.cuda()
        y = torch.matmul(x, x)
        print("✅ GPU tensor operation successful!")
    else:
        print("⚠️  CUDA not available, running on CPU")
except Exception as e:
    print(f"❌ Error: {e}")

print()
