#!/usr/bin/env python3
import sys
sys.path.insert(0, '/Users/sstranburg001/Documents/storm')

from src.actors import detect_actors, detect_tags


def test_step3():
    print("Testing Step 3: Actor and Tag Detection\n")
    
    # Test actor detection
    print("✓ Test 1: Actor detection")
    
    test_cases = [
        ("NVIDIA announces new GPU", ["NVDA"]),
        ("TSMC expands capacity", ["TSM"]),
        ("AWS launches new service", ["AMZN"]),
        ("Google TPU performance", ["GOOGL"]),
        ("Microsoft Azure and Amazon AWS partnership", ["AMZN", "MSFT"]),
    ]
    
    for text, expected in test_cases:
        detected = detect_actors(text)
        assert detected == expected, f"Expected {expected}, got {detected} for '{text}'"
        print(f"  '{text[:40]}...' → {detected}")
    
    # Test tag detection
    print("\n✓ Test 2: Tag detection")
    
    tag_cases = [
        ("CoWoS technology breakthrough", ["advanced_packaging"]),
        ("Custom silicon for AI workloads", ["custom_silicon"]),
        ("Data center power consumption rises", ["ai_infra", "power_constraints"]),
        ("GPU inference efficiency improvements", ["ai_infra", "inference_efficiency"]),
        ("Capital expenditure increases", ["capex"]),
        ("Supply chain constraints", ["supply_chain"]),
        ("AI infrastructure with custom silicon", ["ai_infra", "custom_silicon"]),
    ]
    
    for text, expected in tag_cases:
        detected = detect_tags(text)
        assert detected == expected, f"Expected {expected}, got {detected} for '{text}'"
        print(f"  '{text[:40]}...' → {detected}")
    
    print("\n✅ All Step 3 tests passed!")


if __name__ == "__main__":
    test_step3()
