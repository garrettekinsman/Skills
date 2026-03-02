#!/usr/bin/env python3
"""
Geopolitical Trading Strategies - Convert intelligence into actionable trades
"""

import json
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Any

class GeopoliticalTrader:
    """Convert geopolitical intelligence into specific trading strategies"""
    
    def __init__(self):
        self.active_threats = {}
        self.market_regimes = {
            "risk_on": {"vix": "<20", "oil": "stable", "gold": "declining"},
            "risk_off": {"vix": ">25", "oil": "rising", "gold": "rising"},
            "crisis": {"vix": ">35", "oil": "spiking", "gold": "flight_to_quality"}
        }
    
    def iran_escalation_trades(self, threat_level: int, time_horizon: str = "2_weeks") -> Dict[str, Any]:
        """Generate specific trades for Iran escalation scenarios"""
        
        # Threat level 1-10, time horizon: "1_week", "2_weeks", "1_month"
        
        if threat_level <= 3:
            # Low threat - minor posturing
            return {
                "assessment": "Low probability escalation",
                "action": "Monitor only",
                "reasoning": "Diplomatic noise, not actionable"
            }
        
        elif threat_level <= 6:
            # Moderate threat - hedge existing positions
            base_trades = {
                "oil_hedge": {
                    "strategy": "XLE call debit spread",
                    "strikes": "ATM / +$3",
                    "allocation": "2-3% of portfolio",
                    "rationale": "Energy sector hedge without full commitment"
                },
                "safe_haven": {
                    "strategy": "GLD call debit spread", 
                    "strikes": "ATM / +$5",
                    "allocation": "2% of portfolio",
                    "rationale": "Modest flight-to-quality protection"
                },
                "volatility": {
                    "strategy": "VIX calls (long dated)",
                    "strikes": "25-30 calls",
                    "allocation": "1% of portfolio", 
                    "rationale": "Cheap volatility insurance"
                }
            }
        
        elif threat_level <= 8:
            # High threat - aggressive positioning
            base_trades = {
                "oil_aggressive": {
                    "strategy": "USO call debit spread + XLE calls",
                    "strikes": "USO ATM/+$2, XLE ATM/+$4",
                    "allocation": "5-7% of portfolio",
                    "rationale": "Direct oil exposure + sector play"
                },
                "defense": {
                    "strategy": "ITA call debit spread",
                    "strikes": "ATM / +$10",
                    "allocation": "3-4% of portfolio",
                    "rationale": "Defense contractors benefit from conflict"
                },
                "risk_off": {
                    "strategy": "QQQ put debit spread",
                    "strikes": "ATM / -$15",
                    "allocation": "4-5% of portfolio",
                    "rationale": "Tech vulnerable to risk-off flows"
                },
                "flight_to_quality": {
                    "strategy": "TLT call debit spread",
                    "strikes": "ATM / +$3", 
                    "allocation": "3% of portfolio",
                    "rationale": "Bond rally during crisis"
                }
            }
        
        else:  # threat_level >= 9
            # Critical threat - maximum defensive positioning
            base_trades = {
                "oil_maximum": {
                    "strategy": "Oil futures + energy stocks",
                    "allocation": "10-15% of portfolio",
                    "rationale": "Strait of Hormuz closure risk"
                },
                "crisis_basket": {
                    "strategy": "Gold + bonds + defense",
                    "allocation": "20-25% total",
                    "rationale": "Full crisis portfolio"
                },
                "equity_protection": {
                    "strategy": "SPY put spreads + VIX calls",
                    "allocation": "10% of portfolio",
                    "rationale": "Broad market protection"
                }
            }
        
        # Adjust for time horizon
        if time_horizon == "1_week":
            # Shorter DTE, more aggressive
            for trade in base_trades.values():
                if "allocation" in trade:
                    trade["dte"] = "7-14 days"
                    trade["time_decay_risk"] = "High"
        elif time_horizon == "1_month":
            # Longer DTE, more conservative
            for trade in base_trades.values():
                if "allocation" in trade:
                    trade["dte"] = "30-45 days"
                    trade["time_decay_risk"] = "Low"
        
        return {
            "threat_level": threat_level,
            "time_horizon": time_horizon,
            "trades": base_trades,
            "total_allocation": sum(
                float(trade.get("allocation", "0%").rstrip("% of portfolio").split("-")[0]) 
                for trade in base_trades.values()
                if "allocation" in trade
            ),
            "exit_strategy": {
                "profit_target": "50% of max gain",
                "stop_loss": "50% of premium paid",
                "time_stop": "Close 7 DTE regardless",
                "event_stop": "Close on de-escalation signals"
            }
        }
    
    def escalation_ladder_framework(self) -> Dict[str, Any]:
        """Framework for escalation ladder trading"""
        
        return {
            "level_1_diplomatic": {
                "indicators": ["harsh_statements", "ambassador_recalls", "trade_restrictions"],
                "market_impact": "minimal",
                "action": "monitor_only"
            },
            "level_2_economic": {
                "indicators": ["sanctions", "oil_export_restrictions", "banking_limits"],
                "market_impact": "sector_specific", 
                "action": "small_hedges"
            },
            "level_3_military_posturing": {
                "indicators": ["troop_movements", "naval_deployments", "military_exercises"],
                "market_impact": "risk_premium",
                "action": "moderate_positioning"
            },
            "level_4_proxy_conflict": {
                "indicators": ["militia_attacks", "drone_strikes", "rocket_barrages"],
                "market_impact": "sustained_premium",
                "action": "significant_positioning"
            },
            "level_5_direct_confrontation": {
                "indicators": ["state_on_state_attacks", "infrastructure_targeting", "casualty_events"],
                "market_impact": "crisis_mode",
                "action": "maximum_defensive"
            },
            "level_6_regional_war": {
                "indicators": ["multi_front_conflict", "supply_disruption", "alliance_activation"],
                "market_impact": "global_recession_risk",
                "action": "cash_and_commodities"
            }
        }
    
    def backtest_iran_events(self) -> Dict[str, Any]:
        """Backtest historical Iran-related market moves"""
        
        events = {
            "tanker_war_1987": {
                "context": "Iran-Iraq War, US Navy escort operations",
                "oil_reaction": "+100% (1986-1987)",
                "duration": "18 months",
                "resolution": "UN ceasefire",
                "lessons": "Sustained supply risk = sustained premium"
            },
            "khobar_towers_1996": {
                "context": "Iran-linked bombing of US military housing",
                "oil_reaction": "+8% immediate, +15% over 2 months",
                "duration": "2-3 months",
                "resolution": "Diplomatic isolation, no escalation",
                "lessons": "Terror events fade without supply impact"
            },
            "nuclear_crisis_2012": {
                "context": "EU oil embargo, SWIFT banking restrictions",
                "oil_reaction": "+20% (Jan-Mar 2012)",
                "duration": "6 months",
                "resolution": "Negotiated interim deal",
                "lessons": "Sanctions premium real but negotiable"
            },
            "soleimani_killing_2020": {
                "context": "US drone strike on IRGC Quds Force commander",
                "oil_reaction": "+4% same day, +8% peak",
                "vix_reaction": "+23% to 18.5",
                "gold_reaction": "+2% same day",
                "duration": "5 trading days",
                "resolution": "Iran proportional response, no escalation",
                "lessons": "Single events fade without follow-up"
            },
            "natanz_sabotage_2021": {
                "context": "Suspected Israeli attack on nuclear facility",
                "oil_reaction": "+2% (limited)",
                "duration": "2-3 days",
                "resolution": "Iran restrained response",
                "lessons": "Covert ops have limited market impact"
            }
        }
        
        patterns = {
            "oil_price_impact": {
                "single_event": "+2% to +8% same day",
                "sustained_conflict": "+20% to +100%",
                "supply_disruption": "+50% to +200%",
                "fade_pattern": "50% retracement in 7-14 days if no follow-up"
            },
            "sector_rotation": {
                "defense_stocks": "+5% to +30% depending on severity",
                "airlines": "-3% to -15% (fuel cost concern)",
                "emerging_markets": "-5% to -20% (risk-off)", 
                "gold": "+1% to +10% (safe haven demand)"
            },
            "timing_patterns": {
                "anticipation_premium": "Often exceeds actual event impact",
                "buy_the_rumor": "Markets price in worst case",
                "sell_the_news": "Often relief rally on actual events",
                "attention_span": "7-14 days unless sustained"
            }
        }
        
        return {
            "historical_events": events,
            "market_patterns": patterns,
            "trading_lessons": {
                "position_early": "Build positions on rising tension",
                "size_appropriately": "2-5% per geopolitical theme",
                "take_profits": "Markets overreact, fade quickly",
                "hedge_duration": "Most events resolve in 2-4 weeks",
                "correlation_breaks": "Normal correlations don't hold in crisis"
            }
        }

def generate_iran_monitoring_prompt() -> str:
    """Generate the research loop prompt for Iran monitoring"""
    
    return """
## Real-Time Iran-Israel Escalation Research Loop

You are monitoring a developing geopolitical situation with significant market implications. Follow the intelligence analysis framework.

### CRITICAL MONITORING TARGETS

**Primary Escalation Indicators:**
1. IRGC/Quds Force troop movements (Lebanon, Syria, Iraq)
2. Iranian naval activity in Strait of Hormuz
3. Proxy force readiness (Hezbollah, Houthis, Iraqi militias)
4. Israeli military preparations (reserves called up, F-35 deployments)
5. US military asset positioning (carriers, tankers, air defenses)
6. Nuclear facility security status (Natanz, Fordow, Isfahan)

**OSINT Data Sources (Use Grok for Twitter data extraction):**
- @sentdefender, @IntelCrab, @WarMonitors, @ElintNews
- Search: "Iran Israel military OR strike OR retaliation OR IRGC"
- Search: "Strait Hormuz OR naval OR oil tanker OR maritime"
- Search: "Hezbollah OR militia OR proxy OR rocket OR missile"

**Market Data Integration:**
- Live oil prices (WTI, Brent) via Tradier
- VIX levels and volatility term structure
- Defense sector performance (RTX, LMT, NOC)
- Currency movements (DXY, safe haven flows)

### THREAT ASSESSMENT FRAMEWORK

Rate current threat level 1-10:
- 1-3: Diplomatic rhetoric only
- 4-6: Economic measures, military posturing  
- 7-8: Proxy conflicts, limited strikes
- 9-10: Direct confrontation, supply disruption

### REQUIRED OUTPUTS

1. **Threat Assessment** (confidence scored 0-100%)
2. **Timeline Prediction** (key triggers in next 24-72h)
3. **Market Implications** (sector-specific impacts)
4. **Trading Recommendations** (specific spreads with rationale)
5. **Source Verification** (cross-reference ≥3 independent sources)

### BIAS RESISTANCE PROTOCOLS

- Challenge consensus narrative
- Look for dis/misinformation
- Verify through multiple source types (OSINT, official, market-based)
- Consider economic incentives for conflict/peace
- Historical pattern matching vs current situation

### UPDATE TRIGGERS

Update assessment if:
- Threat level changes by ≥2 points
- New intelligence from credible sources
- Market reaction exceeds normal ranges
- Timeline acceleration/deceleration

GO DEEP. Cross-verify everything. The market is watching.
"""

# Example usage
if __name__ == "__main__":
    trader = GeopoliticalTrader()
    
    # Example: Moderate Iran threat
    iran_trades = trader.iran_escalation_trades(threat_level=6, time_horizon="2_weeks")
    print("Iran Escalation Trades (Threat Level 6):")
    print(json.dumps(iran_trades, indent=2))
    
    # Historical context
    historical = trader.backtest_iran_events()
    print("\nHistorical Iran Events Analysis:")
    for event, data in historical["historical_events"].items():
        print(f"\n{event}:")
        print(f"  Oil: {data['oil_reaction']}")
        print(f"  Duration: {data['duration']}")
        print(f"  Lesson: {data['lessons']}")