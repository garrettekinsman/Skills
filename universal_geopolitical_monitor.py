#!/usr/bin/env python3
"""
Universal Geopolitical Intelligence Monitor
Adaptive framework for any emerging threat - Iran, China, or unknown unknowns
"""

import json
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

@dataclass
class ThreatVector:
    """Generic threat vector that can adapt to any situation"""
    id: str
    region: str
    actors: List[str]
    threat_type: str  # "military", "economic", "cyber", "environmental", "social"
    baseline_threat: float  # 0.0-1.0 baseline risk
    current_threat: float   # 0.0-1.0 current assessment
    trend: str             # "escalating", "stable", "de_escalating"
    confidence: float      # 0.0-1.0 confidence in assessment
    last_updated: datetime
    key_indicators: List[str]
    market_sectors_affected: List[str]

class UniversalGeopoliticalMonitor:
    """Monitor all global threat vectors simultaneously"""
    
    def __init__(self):
        self.global_baselines = self._initialize_global_baselines()
        self.active_threats = self.global_baselines  # Start with baseline threats
        self.monitoring_keywords = self._initialize_universal_keywords()
        self.market_mapping = self._initialize_market_mappings()
        
    def _initialize_global_baselines(self) -> Dict[str, ThreatVector]:
        """Initialize baseline threat monitoring for all major regions/issues"""
        
        baselines = {
            # Traditional hotspots
            "middle_east_iran_israel": ThreatVector(
                id="middle_east_iran_israel",
                region="middle_east", 
                actors=["iran", "israel", "usa", "hezbollah"],
                threat_type="military",
                baseline_threat=0.6,  # Always elevated
                current_threat=0.6,
                trend="stable",
                confidence=0.8,
                last_updated=datetime.now(),
                key_indicators=["irgc_activity", "israeli_strikes", "proxy_attacks"],
                market_sectors_affected=["energy", "defense", "safe_havens"]
            ),
            
            "china_taiwan": ThreatVector(
                id="china_taiwan",
                region="asia_pacific",
                actors=["china", "taiwan", "usa", "japan"],
                threat_type="military", 
                baseline_threat=0.5,
                current_threat=0.5,
                trend="stable",
                confidence=0.7,
                last_updated=datetime.now(),
                key_indicators=["pla_exercises", "strait_transits", "diplomatic_pressure"],
                market_sectors_affected=["semiconductors", "shipping", "defense"]
            ),
            
            "russia_ukraine": ThreatVector(
                id="russia_ukraine", 
                region="eastern_europe",
                actors=["russia", "ukraine", "nato", "eu"],
                threat_type="military",
                baseline_threat=0.7,  # Active conflict
                current_threat=0.7,
                trend="stable", 
                confidence=0.9,
                last_updated=datetime.now(),
                key_indicators=["front_line_activity", "weapons_deliveries", "nato_support"],
                market_sectors_affected=["energy", "agriculture", "defense"]
            ),
            
            "north_korea": ThreatVector(
                id="north_korea",
                region="asia_pacific", 
                actors=["north_korea", "south_korea", "usa", "china"],
                threat_type="military",
                baseline_threat=0.4,
                current_threat=0.4,
                trend="stable",
                confidence=0.6,
                last_updated=datetime.now(),
                key_indicators=["missile_tests", "nuclear_activity", "rhetoric"],
                market_sectors_affected=["asia_pacific_markets", "defense"]
            ),
            
            # Economic/cyber threats
            "us_china_trade": ThreatVector(
                id="us_china_trade",
                region="global",
                actors=["usa", "china"],
                threat_type="economic", 
                baseline_threat=0.5,
                current_threat=0.5,
                trend="stable",
                confidence=0.8,
                last_updated=datetime.now(),
                key_indicators=["tariff_announcements", "tech_restrictions", "trade_volumes"],
                market_sectors_affected=["technology", "manufacturing", "emerging_markets"]
            ),
            
            "global_cyber": ThreatVector(
                id="global_cyber",
                region="global",
                actors=["state_actors", "criminal_groups"],
                threat_type="cyber",
                baseline_threat=0.6,  # Always high
                current_threat=0.6,
                trend="stable", 
                confidence=0.5,  # Hard to assess
                last_updated=datetime.now(),
                key_indicators=["major_breaches", "infrastructure_attacks", "attribution"],
                market_sectors_affected=["technology", "finance", "utilities"]
            ),
            
            # Emerging/wildcard threats  
            "energy_transition_conflicts": ThreatVector(
                id="energy_transition_conflicts",
                region="global",
                actors=["oil_producers", "green_transition_leaders"],
                threat_type="economic",
                baseline_threat=0.3,
                current_threat=0.3,
                trend="stable",
                confidence=0.4,
                last_updated=datetime.now(),
                key_indicators=["renewable_adoption", "oil_demand", "policy_changes"],
                market_sectors_affected=["energy", "materials", "utilities"]
            ),
            
            "ai_geopolitics": ThreatVector(
                id="ai_geopolitics", 
                region="global",
                actors=["usa", "china", "eu", "tech_companies"],
                threat_type="economic", 
                baseline_threat=0.4,
                current_threat=0.4,
                trend="escalating",
                confidence=0.3,  # Very uncertain
                last_updated=datetime.now(),
                key_indicators=["ai_export_controls", "compute_restrictions", "talent_competition"],
                market_sectors_affected=["technology", "semiconductors", "defense"]
            )
        }
        
        return baselines
    
    def _initialize_universal_keywords(self) -> Dict[str, List[str]]:
        """Universal keywords that detect emerging threats across all domains"""
        
        return {
            "escalation_signals": [
                "attack", "strike", "bombing", "missile", "explosion", "casualties",
                "military", "troops", "deployment", "mobilization", "alert", "emergency",
                "sanctions", "embargo", "retaliation", "response", "escalation"
            ],
            "de_escalation_signals": [
                "ceasefire", "truce", "agreement", "negotiation", "dialogue", "diplomacy",
                "talks", "peace", "resolution", "compromise", "de_escalation", "calm"
            ],
            "economic_impact": [
                "sanctions", "trade", "tariff", "embargo", "blockade", "supply chain", 
                "energy", "oil", "gas", "commodity", "currency", "market", "stocks"
            ],
            "breaking_indicators": [
                "breaking", "urgent", "alert", "developing", "confirmed", "reports",
                "sources", "officials", "statement", "announcement", "emergency"
            ],
            "high_confidence": [
                "confirmed", "verified", "official", "statement", "pentagon", "state_dept",
                "ministry", "government", "parliament", "congress", "nato", "un"
            ]
        }
    
    def _initialize_market_mappings(self) -> Dict[str, Dict[str, List[str]]]:
        """Map threat types to affected market sectors"""
        
        return {
            "military_conflict": {
                "bullish": ["defense", "energy", "gold", "safe_havens"],
                "bearish": ["airlines", "tourism", "emerging_markets", "risk_assets"],
                "tickers": ["RTX", "LMT", "NOC", "XLE", "GLD", "TLT", "VIX"]
            },
            "economic_warfare": {
                "bullish": ["domestic_production", "alternative_supply", "safe_havens"],
                "bearish": ["global_trade", "emerging_markets", "affected_sectors"],
                "tickers": ["DXY", "GLD", "EEM", "FXI", "SPY"]
            },
            "cyber_attacks": {
                "bullish": ["cybersecurity", "backup_infrastructure", "physical_assets"],
                "bearish": ["affected_sectors", "cloud_services", "digital_infrastructure"],
                "tickers": ["CIBR", "HACK", "XLU", "XLF"]
            },
            "energy_disruption": {
                "bullish": ["energy", "alternative_energy", "energy_storage"],
                "bearish": ["energy_intensive", "transportation", "chemicals"],
                "tickers": ["XLE", "XOP", "USO", "ICLN", "TSLA"]
            },
            "supply_chain_disruption": {
                "bullish": ["local_production", "inventory_heavy", "logistics"],
                "bearish": ["just_in_time", "global_supply", "manufacturing"],
                "tickers": ["XLI", "UPS", "FDX", "CAT", "DE"]
            }
        }
    
    def detect_emerging_threats(self, osint_data: List[Dict[str, Any]]) -> List[ThreatVector]:
        """Detect new or escalating threats from OSINT data"""
        
        emerging_threats = []
        
        # Analyze message patterns for unknown threats
        for message in osint_data:
            text = message.get("text", "").lower()
            timestamp = message.get("timestamp", datetime.now())
            source = message.get("source", "unknown")
            
            # Check for escalation patterns
            escalation_score = self._calculate_escalation_score(text)
            
            # Check for geographic/actor patterns
            detected_actors = self._extract_actors(text)
            detected_region = self._extract_region(text)
            
            # Check for new threat combinations
            if escalation_score > 0.7 and detected_actors and detected_region:
                # Potential new threat vector
                threat_id = f"{detected_region}_{'-'.join(detected_actors)}"
                
                if threat_id not in self.active_threats:
                    # New emerging threat
                    new_threat = ThreatVector(
                        id=threat_id,
                        region=detected_region,
                        actors=detected_actors,
                        threat_type=self._classify_threat_type(text),
                        baseline_threat=0.3,  # New threats start moderate
                        current_threat=escalation_score,
                        trend="escalating",
                        confidence=0.5,  # Lower confidence for new threats
                        last_updated=timestamp,
                        key_indicators=self._extract_indicators(text),
                        market_sectors_affected=self._predict_market_impact(text)
                    )
                    emerging_threats.append(new_threat)
        
        return emerging_threats
    
    def _calculate_escalation_score(self, text: str) -> float:
        """Calculate escalation score from text content"""
        
        escalation_keywords = self.monitoring_keywords["escalation_signals"]
        breaking_keywords = self.monitoring_keywords["breaking_indicators"]
        
        escalation_count = sum(1 for keyword in escalation_keywords if keyword in text)
        breaking_count = sum(1 for keyword in breaking_keywords if keyword in text)
        
        # Normalize and combine scores
        escalation_score = min(escalation_count / 5, 1.0)  # Max 5 escalation keywords
        breaking_score = min(breaking_count / 3, 1.0)      # Max 3 breaking keywords
        
        return (escalation_score * 0.7) + (breaking_score * 0.3)
    
    def _extract_actors(self, text: str) -> List[str]:
        """Extract country/actor names from text"""
        
        known_actors = [
            "iran", "israel", "usa", "china", "russia", "ukraine", "taiwan",
            "north korea", "south korea", "japan", "india", "pakistan",
            "saudi arabia", "turkey", "egypt", "syria", "lebanon", "iraq",
            "nato", "eu", "un", "irgc", "hezbollah", "hamas"
        ]
        
        detected = [actor for actor in known_actors if actor in text.lower()]
        return detected[:4]  # Limit to 4 main actors
    
    def _extract_region(self, text: str) -> str:
        """Extract primary region from text"""
        
        region_keywords = {
            "middle_east": ["iran", "israel", "saudi", "syria", "lebanon", "iraq", "gulf"],
            "asia_pacific": ["china", "taiwan", "korea", "japan", "south china sea"],
            "europe": ["russia", "ukraine", "nato", "eu", "poland", "germany"],
            "africa": ["sudan", "ethiopia", "somalia", "libya", "egypt"],
            "americas": ["venezuela", "cuba", "mexico", "canada"],
            "global": ["cyber", "space", "maritime", "trade", "climate"]
        }
        
        for region, keywords in region_keywords.items():
            if any(keyword in text.lower() for keyword in keywords):
                return region
        
        return "unknown"
    
    def _classify_threat_type(self, text: str) -> str:
        """Classify the type of threat from text"""
        
        if any(word in text.lower() for word in ["military", "missile", "attack", "strike"]):
            return "military"
        elif any(word in text.lower() for word in ["sanction", "trade", "embargo", "tariff"]):
            return "economic"
        elif any(word in text.lower() for word in ["cyber", "hack", "malware", "breach"]):
            return "cyber"
        elif any(word in text.lower() for word in ["climate", "disaster", "flood", "drought"]):
            return "environmental"
        else:
            return "social"
    
    def _extract_indicators(self, text: str) -> List[str]:
        """Extract key indicators from text"""
        
        # Simple keyword extraction - could be enhanced with NLP
        indicators = []
        
        if "missile" in text.lower():
            indicators.append("missile_activity")
        if "military" in text.lower():
            indicators.append("military_movements")
        if "sanction" in text.lower():
            indicators.append("economic_measures")
        
        return indicators
    
    def _predict_market_impact(self, text: str) -> List[str]:
        """Predict affected market sectors from threat text"""
        
        sectors = []
        
        if any(word in text.lower() for word in ["oil", "energy", "gas"]):
            sectors.append("energy")
        if any(word in text.lower() for word in ["military", "defense", "weapon"]):
            sectors.append("defense")
        if any(word in text.lower() for word in ["tech", "cyber", "semiconductor"]):
            sectors.append("technology")
        if any(word in text.lower() for word in ["trade", "tariff", "export"]):
            sectors.append("global_trade")
        
        return sectors
    
    def generate_global_threat_assessment(self) -> Dict[str, Any]:
        """Generate comprehensive global threat assessment"""
        
        current_time = datetime.now()
        
        # Rank all threats by current risk
        ranked_threats = sorted(
            self.active_threats.values(),
            key=lambda t: t.current_threat * t.confidence,
            reverse=True
        )
        
        # Calculate global risk level
        weighted_risk = sum(
            threat.current_threat * threat.confidence 
            for threat in ranked_threats[:5]  # Top 5 threats
        ) / 5
        
        # Identify trending threats
        escalating = [t for t in ranked_threats if t.trend == "escalating"]
        stable = [t for t in ranked_threats if t.trend == "stable"] 
        de_escalating = [t for t in ranked_threats if t.trend == "de_escalating"]
        
        # Convert emerging threats to serializable format
        emerging_serializable = []
        for t in ranked_threats:
            if (current_time - t.last_updated).days < 7 and t.baseline_threat < 0.4:
                emerging_serializable.append({
                    "id": t.id,
                    "region": t.region,
                    "threat_level": t.current_threat,
                    "confidence": t.confidence
                })

        return {
            "assessment_timestamp": current_time.isoformat(),
            "global_risk_level": min(weighted_risk * 10, 10),  # Scale to 1-10
            "total_monitored_threats": len(self.active_threats),
            "threat_distribution": {
                "escalating": len(escalating),
                "stable": len(stable), 
                "de_escalating": len(de_escalating)
            },
            "top_threats": [
                {
                    "id": t.id,
                    "region": t.region,
                    "actors": t.actors,
                    "current_threat": t.current_threat,
                    "trend": t.trend,
                    "confidence": t.confidence,
                    "market_impact": t.market_sectors_affected
                }
                for t in ranked_threats[:5]
            ],
            "emerging_threats": emerging_serializable,
            "market_implications": self._generate_market_implications(ranked_threats),
            "recommended_monitoring": self._generate_monitoring_recommendations(ranked_threats)
        }
    
    def _generate_market_implications(self, threats: List[ThreatVector]) -> Dict[str, Any]:
        """Generate market implications from current threat landscape"""
        
        # Aggregate sector impacts from all threats
        sector_impacts = {}
        
        for threat in threats[:5]:  # Top 5 threats
            threat_weight = threat.current_threat * threat.confidence
            
            for sector in threat.market_sectors_affected:
                if sector not in sector_impacts:
                    sector_impacts[sector] = 0
                sector_impacts[sector] += threat_weight
        
        # Sort sectors by impact
        sorted_sectors = sorted(sector_impacts.items(), key=lambda x: x[1], reverse=True)
        
        return {
            "sectors_most_affected": sorted_sectors[:5],
            "defensive_positioning": sorted_sectors[:3],
            "risk_on_vs_risk_off": "risk_off" if sector_impacts.get("safe_havens", 0) > 0.5 else "risk_on"
        }
    
    def _generate_monitoring_recommendations(self, threats: List[ThreatVector]) -> Dict[str, Any]:
        """Generate monitoring recommendations based on current threats"""
        
        high_priority = [t for t in threats if t.current_threat > 0.7]
        medium_priority = [t for t in threats if 0.4 <= t.current_threat <= 0.7]
        
        return {
            "immediate_attention": [t.id for t in high_priority],
            "regular_monitoring": [t.id for t in medium_priority],
            "update_frequency": "hourly" if high_priority else "daily",
            "key_indicators_to_watch": list(set(
                indicator 
                for threat in high_priority + medium_priority 
                for indicator in threat.key_indicators
            ))
        }

def create_universal_monitoring_config() -> Dict[str, Any]:
    """Create config for universal geopolitical monitoring"""
    
    return {
        "domain": "intelligence",
        "mode": "streaming",
        "problem_statement": "Monitor global geopolitical threats and identify emerging risks across all domains",
        "success_criteria": [
            "Comprehensive threat landscape assessment",
            "Early detection of emerging threats", 
            "Actionable market implications",
            "Adaptive monitoring based on threat evolution"
        ],
        "resources": {
            "time_budget_minutes": 240,  # 4 hours for global monitoring
            "token_budget": 500000,
            "cost_budget_usd": 20.00,
            "data_sources": ["twitter_osint", "telegram_osint", "news_feeds", "market_data"],
            "models": ["xai/grok-3", "anthropic/claude-sonnet-4", "local/qwen3:32b"]
        },
        "monitoring_domains": {
            "traditional_hotspots": ["middle_east", "asia_pacific", "eastern_europe"],
            "economic_conflicts": ["trade_wars", "sanctions", "supply_chain"],
            "emerging_threats": ["cyber", "climate", "ai_geopolitics", "space"],
            "wildcard_categories": ["unknown_unknowns", "black_swan_events"]
        },
        "real_time": {
            "enabled": True,
            "update_frequency_seconds": 600,  # 10 minutes
            "significance_threshold": 0.3,
            "emergency_threshold": 0.8,
            "alert_channels": ["discord"]
        },
        "adaptive_features": {
            "threat_vector_learning": True,
            "keyword_evolution": True,
            "market_correlation_updating": True,
            "confidence_calibration": True
        }
    }

if __name__ == "__main__":
    monitor = UniversalGeopoliticalMonitor()
    assessment = monitor.generate_global_threat_assessment() 
    
    print("🌍 Universal Geopolitical Threat Assessment")
    print("=" * 50)
    print(json.dumps(assessment, indent=2))