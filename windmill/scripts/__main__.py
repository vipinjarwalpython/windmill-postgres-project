#!/usr/bin/env python3
"""
Entry point for running the pipeline standalone.
Used by:
  - GitHub Actions
  - Docker containers
  - Local command line: python run_pipeline.py

Environment variables override defaults:
  DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME
  SMTP_USER, SMTP_PASS, NOTIFY_EMAIL
"""

import os
import sys

# Add windmill/scripts to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from run_pipeline import main

if __name__ == "__main__":
    # Get values from environment or use defaults
    db_host = os.getenv("DB_HOST", "postgres")
    db_port = int(os.getenv("DB_PORT", "5432"))
    db_user = os.getenv("DB_USER", "windmill")
    db_password = os.getenv("DB_PASSWORD", "windmill123")
    db_name = os.getenv("DB_NAME", "windmill_db")
    
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_pass = os.getenv("SMTP_PASS", "")
    notify_email = os.getenv("NOTIFY_EMAIL", "")
    
    try:
        result = main(
            db_host=db_host,
            db_port=db_port,
            db_user=db_user,
            db_password=db_password,
            db_name=db_name,
            smtp_user=smtp_user,
            smtp_pass=smtp_pass,
            notify_email=notify_email,
        )
        
        print("\n" + "="*60)
        print("Pipeline Execution Summary:")
        print("="*60)
        for key, value in result.items():
            print(f"  {key:20} : {value}")
        print("="*60 + "\n")
        
        sys.exit(0)
        
    except Exception as e:
        print(f"\n❌ Pipeline failed with error:")
        print(f"   {type(e).__name__}: {str(e)}\n")
        import traceback
        traceback.print_exc()
        sys.exit(1)
