#!/usr/bin/env python3
"""
Quick config generator for research loops
Usage: python3 generate_config.py <domain> "<problem_statement>" [output.json]
"""

import sys
import json
from pathlib import Path
from domain_templates import DomainTemplates

def main():
    if len(sys.argv) < 3:
        print(__doc__)
        print("\nAvailable domains:")
        for domain in DomainTemplates.list_domains():
            info = DomainTemplates.get_domain_info(domain)
            print(f"  {domain:<12} - {info['default_mode']} mode, ~{info['typical_duration']} min")
        sys.exit(1)
    
    domain = sys.argv[1]
    problem_statement = sys.argv[2]
    output_file = sys.argv[3] if len(sys.argv) > 3 else None
    
    try:
        config = DomainTemplates.generate_config(domain, problem_statement)
        config_json = json.dumps(config, indent=2)
        
        if output_file:
            with open(output_file, 'w') as f:
                f.write(config_json)
            print(f"Config written to {output_file}")
            
            # Also show preview
            from pathlib import Path
            config_path = Path(output_file).resolve()
            print(f"\nTo preview: python3 loops.py preview {config_path}")
            print(f"To launch:  sessions_spawn with config from {output_file}")
        else:
            print(config_json)
            
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()