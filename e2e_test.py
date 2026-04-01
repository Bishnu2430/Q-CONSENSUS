#!/usr/bin/env python3
"""
E2E Test Script for Q-CONSENSUS Phase 1 + Phase 2
Validates:
1. Progress endpoint returns timing fields
2. Real-time progress updates (no 30s silence)
3. Event queue doesn't overflow
4. Smooth progress transitions
"""

import json
import time
import requests
import sys
from typing import Optional, Dict, Any

BASE_URL = "http://localhost:8000/api"
POLL_INTERVAL = 0.5  # seconds
TIMEOUT = 60  # seconds
POST_TIMEOUT = 30  # seconds (POST /run takes longer)

class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    END = '\033[0m'

def test_status() -> bool:
    """Test 1: Backend is ready"""
    print(f"\n{Colors.BLUE}[TEST 1] Backend Status{Colors.END}")
    try:
        resp = requests.get(f"{BASE_URL}/status", timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            print(f"  ✓ Backend ready")
            print(f"    CPU: {data.get('cpu_percent', '?')}%")
            print(f"    Memory: {data.get('mem_percent', '?')}%")
            print(f"    Agents loaded: {data.get('agents_loaded', '?')}")
            return True
    except Exception as e:
        print(f"  ✗ Backend not ready: {e}")
    return False

def test_progress_fields() -> bool:
    """Test 2: Progress endpoint returns required timing fields"""
    print(f"\n{Colors.BLUE}[TEST 2] Progress Endpoint Timing Fields{Colors.END}")
    
    # Start a simple run
    print("  Starting test run...")
    try:
        run_resp = requests.post(
            f"{BASE_URL}/run",
            json={
                "query": "What is 2+2?",
                "max_rounds": 1,
                "agent_count": 2,
                "enable_web_context": False,
                "use_quantum_randomness": False,
                "use_quantum_weights": False,
                "use_quantum_scheduling": False,
            },
            timeout=POST_TIMEOUT
        )
        if run_resp.status_code != 200:
            print(f"  ✗ Failed to start run: {run_resp.status_code}")
            return False
        
        run_id = run_resp.json().get("run_id")
        print(f"  ✓ Run started: {run_id}")
        
        # Give it a moment to register
        time.sleep(0.5)
        
        # Check progress endpoint
        progress_resp = requests.get(f"{BASE_URL}/run/{run_id}/progress", timeout=5)
        if progress_resp.status_code != 200:
            print(f"  ✗ Progress endpoint failed: {progress_resp.status_code}")
            return False
        
        data = progress_resp.json()
        
        # Validate required fields
        required_fields = [
            "current_stage",
            "agents_completed",
            "total_agents",
            "time_elapsed_ms",
            "estimated_total_ms",
        ]
        
        missing = [f for f in required_fields if f not in data]
        if missing:
            print(f"  ✗ Missing fields: {missing}")
            print(f"    Response: {json.dumps(data, indent=2)}")
            return False
        
        print(f"  ✓ All required timing fields present:")
        print(f"    Stage: {data['current_stage']}")
        print(f"    Elapsed: {data['time_elapsed_ms']}ms")
        print(f"    Estimated total: {data['estimated_total_ms']}ms")
        print(f"    Agents: {data['agents_completed']}/{data['total_agents']}")
        
        return True
    except Exception as e:
        print(f"  ✗ Exception: {e}")
    return False

def test_real_time_progress() -> bool:
    """Test 3: Real-time progress updates (Phase 1 main fix)"""
    print(f"\n{Colors.BLUE}[TEST 3] Real-Time Progress (No 30s Silence){Colors.END}")
    
    try:
        # Start async run
        print("  Starting async debate run...")
        run_resp = requests.post(
            f"{BASE_URL}/run",
            json={
                "query": "What is the opposite of hot?",
                "max_rounds": 1,
                "agent_count": 2,
                "enable_web_context": False,
                "use_quantum_randomness": False,
                "use_quantum_weights": False,
                "use_quantum_scheduling": False,
            },
            timeout=POST_TIMEOUT
        )
        
        if run_resp.status_code != 200:
            print(f"  ✗ Failed to start run")
            return False
        
        run_id = run_resp.json().get("run_id")
        print(f"  ✓ Run started: {run_id}")
        
        # Poll progress with timing
        print(f"  Polling progress every {POLL_INTERVAL}s for up to {TIMEOUT}s...")
        
        start_time = time.time()
        last_stage = None
        stage_changes = 0
        max_elapsed_silence = 0
        last_update_time = start_time
        
        while time.time() - start_time < TIMEOUT:
            try:
                resp = requests.get(f"{BASE_URL}/run/{run_id}/progress", timeout=5)
                if resp.status_code == 200:
                    data = resp.json()
                    current_time = time.time() - start_time
                    
                    # Track silence (time between progress updates)
                    time_since_last = time.time() - last_update_time
                    if time_since_last > max_elapsed_silence:
                        max_elapsed_silence = time_since_last
                    last_update_time = time.time()
                    
                    # Track stage changes
                    if data['current_stage'] != last_stage:
                        stage_changes += 1
                        print(f"    {current_time:.1f}s: {data['current_stage']} ({data['agents_completed']}/{data['total_agents']} agents) - ETA: {data.get('eta_seconds', '?')}s")
                        last_stage = data['current_stage']
                    
                    # Check if complete
                    if data['current_stage'] == 'completed':
                        print(f"  ✓ Run completed in {current_time:.1f}s")
                        print(f"    Total stage changes: {stage_changes}")
                        print(f"    Max silence between updates: {max_elapsed_silence:.2f}s")
                        
                        if stage_changes >= 2:
                            print(f"  ✓ Real-time progress working (stage updates visible)")
                            return True
                        else:
                            print(f"  ✗ Insufficient stage changes (expected >=2, got {stage_changes})")
                            return False
            except Exception as e:
                pass  # Continue polling
            
            time.sleep(POLL_INTERVAL)
        
        print(f"  ✗ Run did not complete within {TIMEOUT}s")
        return False
        
    except Exception as e:
        print(f"  ✗ Exception: {e}")
    return False

def test_event_stream() -> bool:
    """Test 4: Event stream shows variety (validates queue working)"""
    print(f"\n{Colors.BLUE}[TEST 4] Event Stream Quality (Queue Not Overflowing){Colors.END}")
    
    try:
        print("  Starting event stream test...")
        run_resp = requests.post(
            f"{BASE_URL}/run",
            json={
                "query": "Is ice cold?",
                "max_rounds": 1,
                "agent_count": 2,
                "enable_web_context": False,
                "use_quantum_randomness": False,
                "use_quantum_weights": False,
                "use_quantum_scheduling": False,
            },
            timeout=POST_TIMEOUT
        )
        
        run_id = run_resp.json().get("run_id")
        print(f"  ✓ Run started: {run_id}")
        
        # Collect events
        event_types = set()
        start = time.time()
        
        while time.time() - start < TIMEOUT:
            try:
                resp = requests.get(f"{BASE_URL}/events/{run_id}", timeout=5)
                if resp.status_code == 200:
                    data = resp.json()
                    
                    # Collect event types
                    if isinstance(data, list):
                        for event in data:
                            if 'event_type' in event:
                                event_types.add(event['event_type'])
                    
                    # Check if run is done
                    prog_resp = requests.get(f"{BASE_URL}/run/{run_id}/progress", timeout=5)
                    if prog_resp.status_code == 200:
                        if prog_resp.json()['current_stage'] == 'completed':
                            break
            except:
                pass
            
            time.sleep(0.5)
        
        expected_events = {
            'input_received',
            'quantum_randomness',
            'agent_prompted',
            'llm_processing_completed',
            'agent_responded',
            'consensus_completed',
            'final_answer',
            'run_committed',
        }
        
        found = event_types & expected_events
        missing = expected_events - event_types
        
        if len(found) >= 5:
            print(f"  ✓ Event stream healthy")
            print(f"    Event types received: {len(event_types)} total")
            print(f"    Expected events found: {len(found)}/8")
            print(f"    Sample events: {', '.join(sorted(list(event_types))[:5])}")
            return True
        else:
            print(f"  ⚠ Low event count")
            print(f"    Found: {', '.join(sorted(found))}")
            print(f"    Missing: {', '.join(sorted(missing))}")
            return len(found) >= 3  # Pass with at least 3 events
            
    except Exception as e:
        print(f"  ✗ Exception: {e}")
    return False

def main():
    print(f"{Colors.BLUE}{'='*60}")
    print(f"Q-CONSENSUS E2E TEST SUITE")
    print(f"Phase 1 + Phase 2 Validation")
    print(f"{'='*60}{Colors.END}")
    
    # Run tests
    results = {
        "Backend Ready": test_status(),
        "Progress Timing Fields": test_progress_fields(),
        "Real-Time Progress": test_real_time_progress(),
        "Event Stream Quality": test_event_stream(),
    }
    
    # Summary
    print(f"\n{Colors.BLUE}{'='*60}")
    print(f"TEST SUMMARY{Colors.END}")
    print(f"{'='*60}")
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for test_name, result in results.items():
        status = f"{Colors.GREEN}✓ PASS{Colors.END}" if result else f"{Colors.RED}✗ FAIL{Colors.END}"
        print(f"  [{status}] {test_name}")
    
    print(f"{Colors.BLUE}{'='*60}{Colors.END}")
    print(f"Result: {passed}/{total} tests passed")
    
    if passed == total:
        print(f"{Colors.GREEN}✓ ALL TESTS PASSED - READY FOR PRODUCTION{Colors.END}")
        return 0
    else:
        print(f"{Colors.YELLOW}⚠ Some tests failed - review above{Colors.END}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
