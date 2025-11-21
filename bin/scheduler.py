#!/usr/bin/env python3
"""
Background scheduler for periodic database refreshes.
Alternative to cron that runs in the same process as the API server.
"""
import os
import logging
import subprocess
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

def run_refresh():
    """Run the database refresh script"""
    try:
        logger.info("Starting scheduled database refresh...")
        result = subprocess.run(
            ["python3", "/app/bin/refresh_in_container.py"],
            capture_output=True,
            text=True,
            timeout=3600  # 1 hour timeout
        )
        
        if result.returncode == 0:
            logger.info("Database refresh completed successfully")
        else:
            logger.error(f"Database refresh failed with code {result.returncode}")
            logger.error(f"stderr: {result.stderr}")
            
    except subprocess.TimeoutExpired:
        logger.error("Database refresh timed out after 1 hour")
    except Exception as e:
        logger.error(f"Error running database refresh: {e}")

def run_vacuum():
    """Run the weekly VACUUM operation"""
    try:
        logger.info("Starting scheduled VACUUM...")
        db_path = os.getenv("DB", "/app/data/eplus_vc.sqlite3")
        
        result = subprocess.run(
            ["sqlite3", db_path, "PRAGMA wal_checkpoint(TRUNCATE); VACUUM;"],
            capture_output=True,
            text=True,
            timeout=3600
        )
        
        if result.returncode == 0:
            logger.info("VACUUM completed successfully")
        else:
            logger.error(f"VACUUM failed with code {result.returncode}")
            
    except Exception as e:
        logger.error(f"Error running VACUUM: {e}")

def start_scheduler():
    """Initialize and start the background scheduler"""
    scheduler = BackgroundScheduler()
    
    # Schedule refresh 3× daily at 08:05, 14:05, 20:05
    scheduler.add_job(
        run_refresh,
        CronTrigger(hour='8,14,20', minute=5),
        id='refresh_job',
        name='Database Refresh',
        replace_existing=True
    )
    
    # Schedule weekly VACUUM on Sunday at 03:10
    scheduler.add_job(
        run_vacuum,
        CronTrigger(day_of_week='sun', hour=3, minute=10),
        id='vacuum_job',
        name='Weekly VACUUM',
        replace_existing=True
    )
    
    scheduler.start()
    logger.info("Background scheduler started")
    logger.info("Refresh schedule: 08:05, 14:05, 20:05 daily")
    logger.info("VACUUM schedule: Sunday 03:10")
    
    return scheduler
