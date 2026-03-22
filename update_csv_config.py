#!/usr/bin/env python3
"""
Update CSV files in conf.yaml configuration.
This script scans the csv_files directory and updates the data_sources section in conf.yaml.
"""

import os
import yaml

def main():
    # Paths
    project_dir = os.path.dirname(os.path.abspath(__file__))
    csv_dir = os.path.join(project_dir, "csv_files")
    conf_path = os.path.join(project_dir, "conf.yaml")
    
    print(f"Project directory: {project_dir}")
    print(f"CSV files directory: {csv_dir}")
    print(f"Config file: {conf_path}")
    
    # Check if csv_files directory exists
    if not os.path.exists(csv_dir):
        print(f"Error: csv_files directory does not exist: {csv_dir}")
        return
    
    # Scan for CSV/Excel files
    supported_extensions = ['.csv', '.xlsx', '.xls']
    csv_files = []
    
    for filename in os.listdir(csv_dir):
        ext = os.path.splitext(filename)[1].lower()
        if ext in supported_extensions:
            csv_files.append(filename)
            print(f"Found data file: {filename}")
    
    if not csv_files:
        print("Warning: No CSV/Excel files found in csv_files directory")
    
    # Read existing config
    if os.path.exists(conf_path):
        with open(conf_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}
    else:
        config = {}
    
    # Update data_sources
    if 'agents' not in config:
        config['agents'] = {}
    if 'data_sources' not in config['agents']:
        config['agents']['data_sources'] = {}
    if 'search_agent' not in config['agents']['data_sources']:
        config['agents']['data_sources']['search_agent'] = {}
    
    config['agents']['data_sources']['search_agent']['data'] = csv_files
    config['agents']['data_sources']['search_agent']['tables'] = []
    
    # Write updated config
    with open(conf_path, 'w', encoding='utf-8') as f:
        yaml.dump(config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
    
    print(f"\nUpdated conf.yaml with {len(csv_files)} data files:")
    for file in csv_files:
        print(f"  - {file}")
    print("\nUpdated conf.yaml successfully!")

if __name__ == "__main__":
    main()
