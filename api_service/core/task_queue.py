import threading
import queue
import uuid
import time
from enum import Enum
from typing import Dict, Any, Optional, Callable
from core.logger import Logger

logger = Logger.get_logger(__name__)

class TaskStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

class TaskManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(TaskManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
            
        self.task_queue = queue.Queue()
        self.tasks: Dict[str, Dict[str, Any]] = {}
        self.worker_thread = threading.Thread(target=self._worker, daemon=True)
        self.worker_thread.start()
        self._initialized = True
        logger.info("🚀 Task Manager initialized with background worker")

    def add_task(self, task_func: Callable, *args, **kwargs) -> str:
        """
        Add a task to the processing queue.
        Returns the task_id.
        """
        # Extract task_id if provided, otherwise generate one
        task_id = kwargs.get('task_id')
        if not task_id:
            task_id = uuid.uuid4().hex[:8]
            kwargs['task_id'] = task_id
            
        self.tasks[task_id] = {
            "id": task_id,
            "status": TaskStatus.PENDING,
            "submitted_at": time.time(),
            "result": None,
            "error": None
        }
        
        # Add to queue
        self.task_queue.put((task_id, task_func, args, kwargs))
        logger.info(f"📥 Task {task_id} added to queue (Position: {self.task_queue.qsize()})")
        return task_id

    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get the current status and result of a task."""
        return self.tasks.get(task_id)

    def update_task_progress(self, task_id: str, progress: int, message: str = "", result: Any = None):
        """Update the progress of a running task."""
        if task_id in self.tasks:
            self.tasks[task_id]["progress"] = progress
            self.tasks[task_id]["message"] = message
            if result is not None:
                self.tasks[task_id]["result"] = result
            logger.info(f"📈 Task {task_id} progress: {progress}% - {message}")

    def _worker(self):
        """Background worker that processes tasks sequentially."""
        logger.info("👷 Task Worker loop started")
        while True:
            try:
                # Block until a task is available
                task_id, func, args, kwargs = self.task_queue.get()
                
                logger.info(f"🔄 Processing Task {task_id}...")
                self.tasks[task_id]["status"] = TaskStatus.PROCESSING
                self.tasks[task_id]["started_at"] = time.time()
                
                try:
                    # Execute the task
                    result = func(*args, **kwargs)
                    
                    self.tasks[task_id]["status"] = TaskStatus.COMPLETED
                    self.tasks[task_id]["completed_at"] = time.time()
                    self.tasks[task_id]["result"] = result
                    
                    # If the result itself indicates an error (from our app logic)
                    if isinstance(result, dict) and result.get("status") == "error":
                         self.tasks[task_id]["status"] = TaskStatus.FAILED
                         self.tasks[task_id]["error"] = result.get("error")
                    
                    logger.info(f"✅ Task {task_id} completed successfully")
                    
                except Exception as e:
                    import traceback
                    error_trace = traceback.format_exc()
                    logger.error(f"❌ Task {task_id} failed with exception: {e}")
                    logger.error(error_trace)
                    
                    self.tasks[task_id]["status"] = TaskStatus.FAILED
                    self.tasks[task_id]["error"] = str(e)
                    self.tasks[task_id]["traceback"] = error_trace
                    self.tasks[task_id]["completed_at"] = time.time()
                
                finally:
                    self.task_queue.task_done()
                    
            except Exception as e:
                logger.error(f"💀 Critical Worker Error: {e}")
                time.sleep(1) # Prevent tight loop if queue is broken
