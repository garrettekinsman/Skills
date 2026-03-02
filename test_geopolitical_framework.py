#!/usr/bin/env python3
"""
Test Framework for Universal Geopolitical Monitoring
Simulates various crisis scenarios to validate system response
"""

import json
import random
from datetime import datetime, timedelta
from typing import Dict, List, Any
from universal_geopolitical_monitor import UniversalGeopoliticalMonitor, ThreatVector

class GeopoliticalTestFramework:
    """Test the geopolitical monitoring system with simulated scenarios"""
    
    def __init__(self):
        self.monitor = UniversalGeopoliticalMonitor()
        self.test_scenarios = self._create_test_scenarios()
        self.mock_osint_data = self._create_mock_osint_data()
    
    def _create_test_scenarios(self) -> Dict[str, Dict[str, Any]]:
        """Create test scenarios for different crisis types"""
        
        return {
            "iran_escalation": {
                "description": "Iran-Israel escalation with oil supply risk",
                "osint_messages": [
                    {"text": "BREAKING: Israeli jets spotted over Lebanon, heading towards Iranian targets", "source": "@ME_Spectator", "timestamp": datetime.now()},
                    {"text": "URGENT: Iran threatens to close Strait of Hormuz in response to Israeli aggression", "source": "@WarMonitors", "timestamp": datetime.now()},
                    {"text": "US Navy moving additional assets to Persian Gulf region", "source": "@IntelCrab", "timestamp": datetime.now()}
                ],
                "expected_threat_level": 8,
                "expected_sectors": ["energy", "defense", "safe_havens"],
                "expected_trades": ["XLE calls", "GLD calls", "VIX calls"]
            },
            
            "china_taiwan_crisis": {
                "description": "PLA military exercises escalate to blockade scenario",
                "osint_messages": [
                    {"text": "PLA Navy surrounds Taiwan with largest naval exercise in decades", "source": "@Conflicts", "timestamp": datetime.now()},
                    {"text": "Taiwan reports commercial flights being turned away from airspace", "source": "@liveuamap", "timestamp": datetime.now()},
                    {"text": "TSMC halts operations as tensions escalate in Taiwan Strait", "source": "@OSINT_Technical", "timestamp": datetime.now()}
                ],
                "expected_threat_level": 9,
                "expected_sectors": ["semiconductors", "defense", "safe_havens"],
                "expected_trades": ["SMH puts", "RTX calls", "TLT calls"]
            },
            
            "cyber_warfare": {
                "description": "Major cyber attack on critical infrastructure",
                "osint_messages": [
                    {"text": "BREAKING: Major power grid cyber attack reported across Eastern US", "source": "@CyberSecNews", "timestamp": datetime.now()},
                    {"text": "Russian-linked group claims responsibility for infrastructure attack", "source": "@ThreatIntel", "timestamp": datetime.now()},
                    {"text": "Banking systems experiencing widespread outages following cyber event", "source": "@FinSecWatch", "timestamp": datetime.now()}
                ],
                "expected_threat_level": 7,
                "expected_sectors": ["cybersecurity", "utilities", "finance"],
                "expected_trades": ["CIBR calls", "XLU puts", "XLF puts"]
            },
            
            "unknown_unknown": {
                "description": "Completely unexpected crisis in unexpected region",
                "osint_messages": [
                    {"text": "URGENT: Major volcanic eruption in Indonesia disrupts global shipping lanes", "source": "@GeologyAlert", "timestamp": datetime.now()},
                    {"text": "Ash cloud grounds all flights across SE Asia, supply chains severely impacted", "source": "@ShippingNews", "timestamp": datetime.now()},
                    {"text": "Indonesia declares state of emergency, requests international aid", "source": "@BBCBreaking", "timestamp": datetime.now()}
                ],
                "expected_threat_level": 6,
                "expected_sectors": ["shipping", "airlines", "commodities"],
                "expected_trades": ["FDX puts", "DAL puts", "DBA calls"]
            },
            
            "economic_warfare": {
                "description": "Sudden escalation in US-China trade war",
                "osint_messages": [
                    {"text": "BREAKING: US announces complete ban on all Chinese semiconductor imports", "source": "@TradeWar", "timestamp": datetime.now()},
                    {"text": "China retaliates with rare earth export restrictions to US", "source": "@ChinaTrade", "timestamp": datetime.now()},
                    {"text": "Markets in freefall as trade war escalates beyond expectations", "source": "@MarketWatch", "timestamp": datetime.now()}
                ],
                "expected_threat_level": 7,
                "expected_sectors": ["technology", "emerging_markets", "commodities"],
                "expected_trades": ["ASHR puts", "SMH puts", "GLD calls"]
            },
            
            "de_escalation": {
                "description": "Major diplomatic breakthrough reduces tensions",
                "osint_messages": [
                    {"text": "BREAKING: Iran and Israel agree to ceasefire mediated by US", "source": "@DiplomaticNews", "timestamp": datetime.now()},
                    {"text": "Both sides agree to return to nuclear negotiations next week", "source": "@StateNews", "timestamp": datetime.now()},
                    {"text": "Oil prices plummet as Middle East tensions suddenly ease", "source": "@OilMarkets", "timestamp": datetime.now()}
                ],
                "expected_threat_level": 3,
                "expected_sectors": ["risk_assets", "growth_stocks"],
                "expected_trades": ["QQQ calls", "XLE puts", "VIX puts"]
            }
        }
    
    def _create_mock_osint_data(self) -> List[Dict[str, Any]]:
        """Create mock OSINT data for testing"""
        
        return [
            {"text": "routine diplomatic meeting between officials", "source": "@DiploWatch", "timestamp": datetime.now()},
            {"text": "standard military exercise in international waters", "source": "@NavyNews", "timestamp": datetime.now()},
            {"text": "trade negotiations continue at technical level", "source": "@TradeUpdate", "timestamp": datetime.now()}
        ]
    
    def run_scenario_test(self, scenario_name: str) -> Dict[str, Any]:
        """Run a specific test scenario"""
        
        if scenario_name not in self.test_scenarios:
            return {"error": f"Unknown scenario: {scenario_name}"}
        
        scenario = self.test_scenarios[scenario_name]
        
        print(f"\n🧪 TESTING SCENARIO: {scenario['description']}")
        print("=" * 60)
        
        # Simulate OSINT data input
        osint_messages = scenario["osint_messages"]
        
        # Detect emerging threats
        emerging_threats = self.monitor.detect_emerging_threats(osint_messages)
        
        # Update threat levels based on messages
        for message in osint_messages:
            self._update_threats_from_message(message)
        
        # Generate assessment
        assessment = self.monitor.generate_global_threat_assessment()
        
        # Validate results
        validation_results = self._validate_scenario_results(scenario, assessment)
        
        print(f"📊 Test Results:")
        print(f"   Expected Threat Level: {scenario['expected_threat_level']}")
        print(f"   Actual Global Risk: {assessment['global_risk_level']:.1f}")
        print(f"   Expected Sectors: {scenario['expected_sectors']}")
        print(f"   Actual Top Sectors: {[s[0] for s in assessment['market_implications']['sectors_most_affected'][:3]]}")
        print(f"   Validation: {'✅ PASS' if validation_results['passed'] else '❌ FAIL'}")
        
        return {
            "scenario": scenario_name,
            "description": scenario["description"],
            "osint_input": osint_messages,
            "emerging_threats": emerging_threats,
            "global_assessment": assessment,
            "validation": validation_results,
            "test_passed": validation_results["passed"]
        }
    
    def _update_threats_from_message(self, message: Dict[str, Any]):
        """Update threat levels based on message content"""
        
        text = message["text"].lower()
        
        # Simple keyword-based threat updates
        if "iran" in text and "israel" in text:
            if "middle_east_iran_israel" in self.monitor.active_threats:
                threat = self.monitor.active_threats["middle_east_iran_israel"]
                if "breaking" in text or "urgent" in text:
                    threat.current_threat = min(threat.current_threat + 0.3, 1.0)
                    threat.trend = "escalating"
        
        if "china" in text and "taiwan" in text:
            if "china_taiwan" in self.monitor.active_threats:
                threat = self.monitor.active_threats["china_taiwan"]
                if "pla" in text or "blockade" in text:
                    threat.current_threat = min(threat.current_threat + 0.4, 1.0)
                    threat.trend = "escalating"
        
        if "cyber" in text or "hack" in text:
            if "global_cyber" in self.monitor.active_threats:
                threat = self.monitor.active_threats["global_cyber"]
                if "infrastructure" in text or "critical" in text:
                    threat.current_threat = min(threat.current_threat + 0.2, 1.0)
                    threat.trend = "escalating"
    
    def _validate_scenario_results(self, scenario: Dict, assessment: Dict) -> Dict[str, Any]:
        """Validate that the system responded correctly to the scenario"""
        
        validation = {
            "passed": True,
            "issues": []
        }
        
        # Check threat level detection
        global_risk = assessment["global_risk_level"]
        expected_threat = scenario["expected_threat_level"]
        
        if abs(global_risk - expected_threat) > 3:  # Allow 3-point tolerance
            validation["passed"] = False
            validation["issues"].append(f"Threat level mismatch: expected ~{expected_threat}, got {global_risk:.1f}")
        
        # Check sector identification
        top_sectors = [s[0] for s in assessment["market_implications"]["sectors_most_affected"][:5]]
        expected_sectors = scenario["expected_sectors"]
        
        sector_overlap = len(set(top_sectors) & set(expected_sectors))
        if sector_overlap < len(expected_sectors) // 2:  # At least half should match
            validation["passed"] = False
            validation["issues"].append(f"Poor sector detection: expected {expected_sectors}, got {top_sectors}")
        
        return validation
    
    def run_all_tests(self) -> Dict[str, Any]:
        """Run all test scenarios"""
        
        print("🧪 COMPREHENSIVE GEOPOLITICAL FRAMEWORK TESTING")
        print("=" * 70)
        
        results = {}
        passed_count = 0
        
        for scenario_name in self.test_scenarios.keys():
            # Reset monitor state between tests
            self.monitor = UniversalGeopoliticalMonitor()
            
            # Run test
            result = self.run_scenario_test(scenario_name)
            results[scenario_name] = result
            
            if result["test_passed"]:
                passed_count += 1
        
        overall_results = {
            "total_tests": len(self.test_scenarios),
            "tests_passed": passed_count,
            "pass_rate": passed_count / len(self.test_scenarios),
            "individual_results": results
        }
        
        print(f"\n📋 OVERALL TEST RESULTS")
        print(f"=" * 30)
        print(f"Tests Passed: {passed_count}/{len(self.test_scenarios)} ({overall_results['pass_rate']*100:.1f}%)")
        
        if overall_results["pass_rate"] >= 0.8:
            print("✅ FRAMEWORK VALIDATION: PASSED")
        else:
            print("❌ FRAMEWORK VALIDATION: NEEDS IMPROVEMENT")
        
        return overall_results
    
    def test_real_time_monitoring(self) -> Dict[str, Any]:
        """Test the real-time monitoring capabilities"""
        
        print("\n🔄 TESTING REAL-TIME MONITORING")
        print("=" * 40)
        
        # Simulate a sequence of escalating events
        escalation_sequence = [
            {"time": 0, "message": "Routine diplomatic activity", "expected_level": 4},
            {"time": 1, "message": "BREAKING: Military movements reported", "expected_level": 5},
            {"time": 2, "message": "URGENT: Shots fired at border crossing", "expected_level": 6},
            {"time": 3, "message": "ALERT: Full military mobilization declared", "expected_level": 8},
            {"time": 4, "message": "Ceasefire negotiations begin", "expected_level": 6},
            {"time": 5, "message": "Peace agreement signed", "expected_level": 4}
        ]
        
        monitoring_results = []
        
        for event in escalation_sequence:
            # Simulate message processing
            mock_message = {
                "text": event["message"],
                "source": "@TestSource",
                "timestamp": datetime.now()
            }
            
            # Update threats
            self._update_threats_from_message(mock_message)
            
            # Get assessment
            assessment = self.monitor.generate_global_threat_assessment()
            
            monitoring_results.append({
                "time_step": event["time"],
                "input_message": event["message"],
                "detected_threat_level": assessment["global_risk_level"],
                "expected_level": event["expected_level"],
                "response_appropriate": abs(assessment["global_risk_level"] - event["expected_level"]) <= 2
            })
            
            print(f"T+{event['time']}: {event['message'][:40]}... → Risk: {assessment['global_risk_level']:.1f}")
        
        # Calculate responsiveness
        appropriate_responses = sum(1 for r in monitoring_results if r["response_appropriate"])
        responsiveness = appropriate_responses / len(monitoring_results)
        
        return {
            "monitoring_sequence": monitoring_results,
            "responsiveness_rate": responsiveness,
            "real_time_test_passed": responsiveness >= 0.8
        }

def run_integration_test():
    """Run a comprehensive integration test"""
    
    print("🚀 GEOPOLITICAL MONITORING INTEGRATION TEST")
    print("=" * 60)
    
    framework = GeopoliticalTestFramework()
    
    # Test 1: Baseline assessment
    print("\n1. Testing baseline threat assessment...")
    baseline = framework.monitor.generate_global_threat_assessment()
    print(f"   Baseline global risk: {baseline['global_risk_level']:.1f}/10")
    print(f"   Monitoring {baseline['total_monitored_threats']} threat vectors")
    
    # Test 2: Scenario testing
    print("\n2. Running scenario tests...")
    scenario_results = framework.run_all_tests()
    
    # Test 3: Real-time monitoring
    print("\n3. Testing real-time responsiveness...")
    realtime_results = framework.test_real_time_monitoring()
    
    # Overall assessment
    print(f"\n📊 INTEGRATION TEST SUMMARY")
    print(f"=" * 35)
    print(f"Scenario Tests: {scenario_results['pass_rate']*100:.1f}% pass rate")
    print(f"Real-time Monitoring: {realtime_results['responsiveness_rate']*100:.1f}% responsive")
    
    overall_pass = (
        scenario_results['pass_rate'] >= 0.8 and 
        realtime_results['real_time_test_passed']
    )
    
    print(f"Overall Integration: {'✅ PASSED' if overall_pass else '❌ NEEDS WORK'}")
    
    return {
        "baseline_assessment": baseline,
        "scenario_testing": scenario_results,
        "realtime_testing": realtime_results,
        "integration_passed": overall_pass
    }

if __name__ == "__main__":
    results = run_integration_test()
    
    # Save detailed results
    with open('/tmp/geopolitical_test_results.json', 'w') as f:
        json.dumps(results, f, indent=2, default=str)
    
    print(f"\nDetailed results saved to: /tmp/geopolitical_test_results.json")