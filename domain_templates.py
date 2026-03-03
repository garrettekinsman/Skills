#!/usr/bin/env python3
"""
Domain-specific templates for the generalized research loop framework
"""

import json
import datetime
from typing import Dict, List, Any

class DomainTemplates:
    """Generate domain-specific research loop configurations"""
    
    TEMPLATES = {
        "financial": {
            "default_config": {
                "domain": "financial",
                "mode": "hybrid",
                "resources": {
                    "time_budget_minutes": 45,
                    "token_budget": 75000,
                    "cost_budget_usd": 3.00,
                    "data_sources": ["market_data_api", "yfinance", "web_search"],
                    "models": ["xai/grok-4-fast-reasoning", "anthropic/claude-sonnet-4"]
                },
                "real_time": {
                    "enabled": True,
                    "update_frequency_seconds": 300,
                    "significance_threshold": 0.10,
                    "alert_channels": ["discord"]
                },
                "validation": {
                    "cross_source_required": True,
                    "adversarial_testing": True,
                    "bias_resistance": True,
                    "backtest_required": True,
                    "scenario_analysis": ["bull", "bear", "sideways"],
                    "risk_metrics": ["sharpe", "sortino", "max_drawdown"]
                },
                "output": {
                    "format": "brief",
                    "delivery": ["file", "discord"],
                    "include_trade_setups": True,
                    "include_risk_analysis": True
                }
            },
            "success_criteria_templates": [
                "Risk/reward ratio >{ratio}:1",
                "Win probability >{prob}%",
                "Position size ≤{size}% portfolio",
                "Maximum drawdown <{dd}%",
                "Sharpe ratio >{sharpe}"
            ]
        },
        
        "technical": {
            "default_config": {
                "domain": "technical",
                "mode": "batch",
                "resources": {
                    "time_budget_minutes": 90,
                    "token_budget": 100000,
                    "cost_budget_usd": 4.00,
                    "data_sources": ["github", "docs", "web_fetch"],
                    "models": ["anthropic/claude-sonnet-4", "local/qwen3:32b"]
                },
                "real_time": {
                    "enabled": False,
                    "update_frequency_seconds": 3600,
                    "significance_threshold": 0.20
                },
                "validation": {
                    "cross_source_required": True,
                    "adversarial_testing": True,
                    "load_testing": True,
                    "security_audit": True,
                    "cost_modeling": True,
                    "scalability_analysis": True
                },
                "output": {
                    "format": "detailed",
                    "delivery": ["file"],
                    "include_architecture_diagrams": True,
                    "include_implementation_roadmap": True
                }
            },
            "success_criteria_templates": [
                "Handles {load} requests/second with <{latency}ms latency",
                "{uptime}% uptime achievable",
                "Cost <${cost}/month at target scale",
                "Security compliant with {standard}",
                "Scales to {scale}x current load"
            ]
        },
        
        "product": {
            "default_config": {
                "domain": "product",
                "mode": "hybrid",
                "resources": {
                    "time_budget_minutes": 120,
                    "token_budget": 150000,
                    "cost_budget_usd": 6.00,
                    "data_sources": ["analytics", "user_interviews", "surveys", "web_search"],
                    "models": ["anthropic/claude-opus", "xai/grok-4-fast-reasoning"]
                },
                "real_time": {
                    "enabled": True,
                    "update_frequency_seconds": 1800,
                    "significance_threshold": 0.15,
                    "alert_channels": ["discord", "email"]
                },
                "validation": {
                    "cross_source_required": True,
                    "adversarial_testing": True,
                    "ab_testing": True,
                    "user_feedback": True,
                    "market_research": True
                },
                "output": {
                    "format": "detailed",
                    "delivery": ["file", "dashboard"],
                    "include_user_personas": True,
                    "include_feature_specs": True,
                    "include_go_to_market": True
                }
            },
            "success_criteria_templates": [
                "User satisfaction >{rating}/5.0",
                "Feature adoption >{adoption}% within {timeframe}",
                "Revenue impact ${revenue} annually",
                "Development cost <{dev_cost} engineer-months",
                "Time to market <{ttm} weeks"
            ]
        },
        
        "scientific": {
            "default_config": {
                "domain": "scientific",
                "mode": "batch",
                "resources": {
                    "time_budget_minutes": 180,
                    "token_budget": 200000,
                    "cost_budget_usd": 8.00,
                    "data_sources": ["papers", "datasets", "web_search"],
                    "models": ["anthropic/claude-opus", "local/qwen3:32b"]
                },
                "real_time": {
                    "enabled": False,
                    "update_frequency_seconds": 86400,
                    "significance_threshold": 0.25
                },
                "validation": {
                    "cross_source_required": True,
                    "adversarial_testing": True,
                    "peer_review": True,
                    "reproducibility": True,
                    "statistical_significance": True
                },
                "output": {
                    "format": "detailed",
                    "delivery": ["file"],
                    "include_methodology": True,
                    "include_citations": True,
                    "include_experimental_design": True
                }
            },
            "success_criteria_templates": [
                "Statistical significance p<{p_value}",
                "Effect size >{effect_size}",
                "Reproducible across {n_studies} independent studies",
                "Peer review score >{score}/10",
                "Practical significance in {domain}"
            ]
        },
        
        "intelligence": {
            "default_config": {
                "domain": "intelligence",
                "mode": "streaming",
                "resources": {
                    "time_budget_minutes": 60,
                    "token_budget": 100000,
                    "cost_budget_usd": 4.00,
                    "data_sources": ["osint", "news", "social_media", "web_search"],
                    "models": ["xai/grok-4-fast-reasoning", "anthropic/claude-sonnet-4"]
                },
                "real_time": {
                    "enabled": True,
                    "update_frequency_seconds": 180,
                    "significance_threshold": 0.05,
                    "alert_channels": ["discord", "secure_channel"]
                },
                "validation": {
                    "cross_source_required": True,
                    "adversarial_testing": True,
                    "source_credibility": True,
                    "timeline_analysis": True,
                    "bias_detection": True
                },
                "output": {
                    "format": "brief",
                    "delivery": ["secure_file", "encrypted_message"],
                    "include_threat_assessment": True,
                    "include_confidence_scores": True,
                    "include_action_recommendations": True
                }
            },
            "success_criteria_templates": [
                "Source credibility >{credibility}%",
                "Cross-confirmation from >{sources} independent sources",
                "Timeline consistency verified",
                "Threat level assessment: {threat_level}",
                "Action recommended within {time_limit} hours"
            ]
        }
    }
    
    @classmethod
    def generate_config(cls, domain: str, problem_statement: str, 
                       custom_params: Dict[str, Any] = None) -> Dict[str, Any]:
        """Generate a research loop config for a specific domain and problem"""
        
        if domain not in cls.TEMPLATES:
            raise ValueError(f"Unknown domain: {domain}. Available: {list(cls.TEMPLATES.keys())}")
        
        # Start with domain template
        config = cls.TEMPLATES[domain]["default_config"].copy()
        
        # Add problem-specific details
        config["problem_statement"] = problem_statement
        config["created_at"] = datetime.datetime.now().isoformat()
        
        # Generate success criteria based on template
        config["success_criteria"] = cls._generate_success_criteria(domain, custom_params or {})
        
        # Apply custom overrides
        if custom_params:
            config = cls._merge_config(config, custom_params)
        
        return config
    
    @classmethod
    def _generate_success_criteria(cls, domain: str, params: Dict[str, Any]) -> List[str]:
        """Generate success criteria from templates with parameter substitution"""
        templates = cls.TEMPLATES[domain]["success_criteria_templates"]
        criteria = []
        
        # Default parameter values by domain
        defaults = {
            "financial": {"ratio": 2, "prob": 60, "size": 10, "dd": 20, "sharpe": 1.0},
            "technical": {"load": 1000, "latency": 100, "uptime": 99.9, "cost": 1000, "scale": 10},
            "product": {"rating": 4.0, "adoption": 30, "revenue": 100000, "dev_cost": 3, "ttm": 8},
            "scientific": {"p_value": 0.05, "effect_size": 0.3, "n_studies": 3, "score": 7.0},
            "intelligence": {"credibility": 80, "sources": 3, "threat_level": "MEDIUM", "time_limit": 24}
        }
        
        # Merge defaults with user params
        merged_params = {**defaults.get(domain, {}), **params}
        
        # Substitute parameters into templates
        for template in templates:
            try:
                criteria.append(template.format(**merged_params))
            except KeyError as e:
                # Skip templates with missing parameters
                continue
        
        return criteria
    
    @classmethod
    def _merge_config(cls, base_config: Dict[str, Any], 
                     overrides: Dict[str, Any]) -> Dict[str, Any]:
        """Deep merge configuration dictionaries"""
        result = base_config.copy()
        
        for key, value in overrides.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = cls._merge_config(result[key], value)
            else:
                result[key] = value
        
        return result
    
    @classmethod
    def list_domains(cls) -> List[str]:
        """Get available domain templates"""
        return list(cls.TEMPLATES.keys())
    
    @classmethod
    def get_domain_info(cls, domain: str) -> Dict[str, Any]:
        """Get information about a domain template"""
        if domain not in cls.TEMPLATES:
            raise ValueError(f"Unknown domain: {domain}")
        
        template = cls.TEMPLATES[domain]
        return {
            "domain": domain,
            "default_mode": template["default_config"]["mode"],
            "typical_duration": template["default_config"]["resources"]["time_budget_minutes"],
            "success_criteria_templates": template["success_criteria_templates"],
            "data_sources": template["default_config"]["resources"]["data_sources"]
        }

def main():
    """CLI interface for domain templates"""
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: domain_templates.py <command> [args...]")
        print("Commands:")
        print("  list - List available domains")
        print("  info <domain> - Get domain information")
        print("  generate <domain> <problem_statement> [params.json] - Generate config")
        return
    
    command = sys.argv[1]
    
    if command == "list":
        print("Available domains:")
        for domain in DomainTemplates.list_domains():
            print(f"  {domain}")
    
    elif command == "info":
        if len(sys.argv) < 3:
            print("Usage: domain_templates.py info <domain>")
            return
        
        domain = sys.argv[2]
        try:
            info = DomainTemplates.get_domain_info(domain)
            print(json.dumps(info, indent=2))
        except ValueError as e:
            print(f"Error: {e}")
    
    elif command == "generate":
        if len(sys.argv) < 4:
            print("Usage: domain_templates.py generate <domain> <problem_statement> [params.json]")
            return
        
        domain = sys.argv[2]
        problem = sys.argv[3]
        
        # Load custom params if provided
        custom_params = {}
        if len(sys.argv) > 4:
            try:
                with open(sys.argv[4], 'r') as f:
                    custom_params = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError) as e:
                print(f"Error loading params: {e}")
                return
        
        try:
            config = DomainTemplates.generate_config(domain, problem, custom_params)
            print(json.dumps(config, indent=2))
        except ValueError as e:
            print(f"Error: {e}")
    
    else:
        print(f"Unknown command: {command}")

if __name__ == "__main__":
    main()