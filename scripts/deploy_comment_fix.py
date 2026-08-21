#!/usr/bin/env python3
"""
Deployment script to fix comment system issues:
1. Apply migration for missing Comment fields
2. Restart the application
"""

import subprocess
import sys
import os

def run_command(command, cwd=None):
    """Run a command and return the result"""
    try:
        result = subprocess.run(command, shell=True, check=True, 
                              capture_output=True, text=True, cwd=cwd)
        print(f"SUCCESS: {command}")
        print(result.stdout)
        return True
    except subprocess.CalledProcessError as e:
        print(f"ERROR: {command}")
        print(f"Return code: {e.returncode}")
        print(f"Error output: {e.stderr}")
        return False

def main():
    print("=== Comment System Fix Deployment ===")
    
    # Change to backend directory
    backend_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(backend_dir)
    
    print(f"Working directory: {os.getcwd()}")
    
    # Step 1: Apply the migration
    print("\n1. Applying migration for missing Comment fields...")
    if not run_command("python manage.py migrate api 0041"):
        print("Failed to apply migration")
        sys.exit(1)
    
    # Step 2: Apply any remaining migrations
    print("\n2. Applying all remaining migrations...")
    if not run_command("python manage.py migrate"):
        print("Failed to apply remaining migrations")
        sys.exit(1)
    
    print("\n=== Migration completed successfully! ===")
    print("The comment system should now work properly.")
    print("Please restart your application server if needed.")

if __name__ == "__main__":
    main()
