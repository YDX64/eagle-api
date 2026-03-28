"""
Multi-Source Data Manager with Dynamic Prioritization

Bu modül, birden fazla data source'u yönetir ve hata oranlarına göre
dinamik olarak önceliklendirme yapar.

Features:
- Multi-source URL management
- Health tracking (success/fail metrics)
- Dynamic prioritization based on error rates
- Automatic primary/fallback swapping
- Thread-safe operations
- Redis-backed metrics (fallback to memory)

Author: AI Assistant
Date: 2025-11-03
"""

import os
import time
import logging
import threading
from typing import List, Dict, Optional, Tuple
from datetime import datetime
from collections import deque, defaultdict

logger = logging.getLogger(__name__)

# Singleton instance
_source_manager_instance = None
_source_manager_lock = threading.Lock()


class SourceHealthMetrics:
    """
    Health metrics for a single data source

    Tracks success/failure rates, consecutive failures, and priority score
    """

    def __init__(self, source_url: str, window_size: int = 100):
        """
        Initialize health metrics for a source

        Args:
            source_url: The base URL of the data source
            window_size: Size of sliding window for metrics (default: 100)
        """
        self.source_url = source_url
        self.window_size = window_size

        # Sliding window for request results (True=success, False=failure)
        self.request_history = deque(maxlen=window_size)

        # Counters
        self.total_requests = 0
        self.successful_requests = 0
        self.failed_requests = 0
        self.consecutive_failures = 0

        # Error type tracking
        self.error_types = defaultdict(int)  # {error_type: count}

        # Timestamps
        self.last_success_time = None
        self.last_failure_time = None
        self.last_error = None

        # Thread lock for this source (RLock allows reentrant locking)
        self.lock = threading.RLock()

    def record_success(self):
        """Record a successful request"""
        with self.lock:
            self.request_history.append(True)
            self.total_requests += 1
            self.successful_requests += 1
            self.consecutive_failures = 0
            self.last_success_time = datetime.utcnow()

            logger.debug(f"✅ Success recorded for {self.source_url} "
                        f"(total: {self.total_requests}, success: {self.successful_requests})")

    def record_failure(self, error_type: str = 'unknown'):
        """
        Record a failed request

        Args:
            error_type: Type of error (timeout, 404, 500, etc.)
        """
        with self.lock:
            self.request_history.append(False)
            self.total_requests += 1
            self.failed_requests += 1
            self.consecutive_failures += 1
            self.last_failure_time = datetime.utcnow()
            self.last_error = error_type
            self.error_types[error_type] += 1

            logger.debug(f"❌ Failure recorded for {self.source_url} "
                        f"(type: {error_type}, consecutive: {self.consecutive_failures})")

    def is_circuit_open(self, threshold: int = 5, cooldown: int = 120) -> bool:
        """
        Circuit breaker: skip this source if too many consecutive connection failures.

        After 'threshold' consecutive failures, the source is "open" (skipped)
        for 'cooldown' seconds. After cooldown, one request is allowed through
        (half-open) to test if source recovered.

        Args:
            threshold: Consecutive failures to trip the breaker (default: 5)
            cooldown: Seconds to wait before retrying (default: 120)

        Returns:
            bool: True if source should be skipped
        """
        with self.lock:
            if self.consecutive_failures < threshold:
                return False

            # Circuit is tripped - check if cooldown has passed
            if self.last_failure_time:
                elapsed = (datetime.utcnow() - self.last_failure_time).total_seconds()
                if elapsed < cooldown:
                    return True  # Still in cooldown, skip this source

            # Cooldown passed - allow one attempt (half-open)
            return False

    def get_error_rate(self) -> float:
        """
        Calculate current error rate based on sliding window

        Returns:
            float: Error rate (0.0 to 1.0)
        """
        with self.lock:
            if len(self.request_history) == 0:
                return 0.0

            failures = sum(1 for success in self.request_history if not success)
            error_rate = failures / len(self.request_history)

            return error_rate

    def get_priority_score(self) -> float:
        """
        Calculate priority score for this source

        Priority = (1 - error_rate) * 100
        Higher score = higher priority

        Returns:
            float: Priority score (0-100)
        """
        error_rate = self.get_error_rate()
        priority = (1 - error_rate) * 100

        return round(priority, 2)

    def get_metrics_dict(self) -> Dict:
        """
        Get all metrics as a dictionary

        Returns:
            dict: All metrics for this source
        """
        with self.lock:
            return {
                'source_url': self.source_url,
                'total_requests': self.total_requests,
                'successful_requests': self.successful_requests,
                'failed_requests': self.failed_requests,
                'error_rate': round(self.get_error_rate(), 4),
                'priority_score': self.get_priority_score(),
                'consecutive_failures': self.consecutive_failures,
                'last_success_time': self.last_success_time.isoformat() if self.last_success_time else None,
                'last_failure_time': self.last_failure_time.isoformat() if self.last_failure_time else None,
                'last_error': self.last_error,
                'error_types': dict(self.error_types),
                'circuit_breaker_open': self.is_circuit_open(),
                'window_size': self.window_size,
                'current_window_length': len(self.request_history)
            }

    def reset_metrics(self):
        """Reset all metrics (for testing or manual intervention)"""
        with self.lock:
            self.request_history.clear()
            self.total_requests = 0
            self.successful_requests = 0
            self.failed_requests = 0
            self.consecutive_failures = 0
            self.error_types.clear()
            self.last_success_time = None
            self.last_failure_time = None
            self.last_error = None

            logger.info(f"🔄 Metrics reset for {self.source_url}")


class SourceManager:
    """
    Multi-Source Manager with Dynamic Prioritization

    Manages multiple data sources, tracks their health, and automatically
    switches between them based on error rates.
    """

    def __init__(self):
        """Initialize source manager with environment configuration"""
        # Load configuration from environment
        self.primary_source = os.getenv('PRIMARY_DATA_SOURCE', 'https://live.nowgoal26.com')
        fallback_sources_str = os.getenv('FALLBACK_DATA_SOURCES', 'https://www.goaloo.com')
        self.fallback_sources = [s.strip() for s in fallback_sources_str.split(',') if s.strip()]

        # All sources (primary + fallbacks)
        self.all_sources = [self.primary_source] + self.fallback_sources

        # Configuration
        self.window_size = int(os.getenv('SOURCE_HEALTH_WINDOW', 100))
        self.health_threshold = float(os.getenv('SOURCE_HEALTH_THRESHOLD', 0.3))
        self.consecutive_fail_threshold = int(os.getenv('CONSECUTIVE_FAIL_THRESHOLD', 10))
        self.min_swap_interval = int(os.getenv('MIN_SWAP_INTERVAL', 300))  # seconds

        # Health metrics for each source
        self.source_metrics: Dict[str, SourceHealthMetrics] = {}
        for source in self.all_sources:
            self.source_metrics[source] = SourceHealthMetrics(source, self.window_size)

        # Current primary source (can change dynamically)
        self.current_primary = self.primary_source

        # Last swap time (to prevent too frequent swapping)
        self.last_swap_time = None

        # Thread lock for manager-level operations
        self.manager_lock = threading.Lock()

        logger.info(f"🚀 SourceManager initialized")
        logger.info(f"   Primary: {self.primary_source}")
        logger.info(f"   Fallbacks: {self.fallback_sources}")
        logger.info(f"   Health window: {self.window_size}")
        logger.info(f"   Health threshold: {self.health_threshold}")
        logger.info(f"   Consecutive fail threshold: {self.consecutive_fail_threshold}")

    def get_prioritized_sources(self) -> List[str]:
        """
        Get sources sorted by priority (highest first)

        Current primary is always first, followed by others sorted by priority score.
        Sources with open circuit breakers are filtered out (unless all would be filtered).

        Returns:
            List[str]: Sorted list of source URLs
        """
        with self.manager_lock:
            # Check if we should swap primary
            self._check_and_swap_primary()

            # Current primary is always first
            prioritized = [self.current_primary]

            # Sort other sources by priority score
            other_sources = [s for s in self.all_sources if s != self.current_primary]
            other_sources.sort(
                key=lambda s: self.source_metrics[s].get_priority_score(),
                reverse=True
            )

            prioritized.extend(other_sources)

            # Filter out sources with open circuit breakers
            active_sources = [
                s for s in prioritized
                if not self.source_metrics[s].is_circuit_open()
            ]

            # Safety: never return empty list - if all circuits open, use all sources
            if not active_sources:
                logger.warning("⚡ All circuits open! Using all sources as fallback.")
                active_sources = prioritized
            elif len(active_sources) < len(prioritized):
                skipped = [s for s in prioritized if s not in active_sources]
                logger.info(f"⚡ Circuit breaker skipping: {skipped}")

            logger.debug(f"📊 Active sources: {active_sources}")

            return active_sources

    def record_success(self, source_url: str):
        """
        Record a successful request for a source

        Args:
            source_url: The source URL that succeeded
        """
        if source_url in self.source_metrics:
            self.source_metrics[source_url].record_success()
        else:
            logger.warning(f"⚠️ Attempted to record success for unknown source: {source_url}")

    def record_failure(self, source_url: str, error_type: str = 'unknown'):
        """
        Record a failed request for a source

        Args:
            source_url: The source URL that failed
            error_type: Type of error (timeout, 404, 500, etc.)
        """
        if source_url in self.source_metrics:
            self.source_metrics[source_url].record_failure(error_type)

            # Check if we need to swap primary after this failure
            with self.manager_lock:
                self._check_and_swap_primary()
        else:
            logger.warning(f"⚠️ Attempted to record failure for unknown source: {source_url}")

    def get_health_metrics(self) -> Dict[str, Dict]:
        """
        Get health metrics for all sources

        Returns:
            dict: Metrics for all sources with is_primary flag
        """
        with self.manager_lock:
            metrics = {}
            for source_url, source_metrics in self.source_metrics.items():
                metric_dict = source_metrics.get_metrics_dict()
                metric_dict['is_primary'] = (source_url == self.current_primary)
                metrics[source_url] = metric_dict

            return metrics

    def should_swap_primary(self) -> Tuple[bool, Optional[str]]:
        """
        Determine if primary source should be swapped

        Returns:
            Tuple[bool, Optional[str]]: (should_swap, new_primary_url)
        """
        # Don't swap if we just swapped recently
        if self.last_swap_time:
            time_since_swap = (datetime.utcnow() - self.last_swap_time).total_seconds()
            if time_since_swap < self.min_swap_interval:
                logger.debug(f"⏳ Too soon to swap (last swap: {int(time_since_swap)}s ago)")
                return False, None

        current_primary_metrics = self.source_metrics[self.current_primary]

        # Reason 1: Too many consecutive failures
        if current_primary_metrics.consecutive_failures >= self.consecutive_fail_threshold:
            logger.warning(
                f"🔄 Primary source has {current_primary_metrics.consecutive_failures} "
                f"consecutive failures (threshold: {self.consecutive_fail_threshold})"
            )
            return True, self._select_best_alternative()

        # Reason 2: Error rate too high
        error_rate = current_primary_metrics.get_error_rate()
        if error_rate > self.health_threshold:
            logger.warning(
                f"🔄 Primary source error rate too high: {error_rate:.2%} "
                f"(threshold: {self.health_threshold:.2%})"
            )
            return True, self._select_best_alternative()

        return False, None

    def _select_best_alternative(self) -> Optional[str]:
        """
        Select the best alternative source based on priority scores

        Returns:
            Optional[str]: URL of best alternative, or None if no good alternatives
        """
        alternatives = [s for s in self.all_sources if s != self.current_primary]

        if not alternatives:
            logger.error("❌ No alternative sources available!")
            return None

        # Sort by priority score
        alternatives.sort(
            key=lambda s: self.source_metrics[s].get_priority_score(),
            reverse=True
        )

        best_alternative = alternatives[0]
        best_score = self.source_metrics[best_alternative].get_priority_score()

        logger.info(f"✅ Best alternative: {best_alternative} (score: {best_score})")

        return best_alternative

    def _check_and_swap_primary(self):
        """
        Check if primary should be swapped and perform swap if needed

        This method should be called with manager_lock held
        """
        should_swap, new_primary = self.should_swap_primary()

        if should_swap and new_primary:
            old_primary = self.current_primary
            self.current_primary = new_primary
            self.last_swap_time = datetime.utcnow()

            logger.warning(
                f"🔄 PRIMARY SOURCE SWAPPED: {old_primary} → {new_primary}"
            )

            # Log metrics for both sources
            old_metrics = self.source_metrics[old_primary].get_metrics_dict()
            new_metrics = self.source_metrics[new_primary].get_metrics_dict()

            logger.info(f"   Old primary metrics: error_rate={old_metrics['error_rate']:.2%}, "
                       f"consecutive_failures={old_metrics['consecutive_failures']}")
            logger.info(f"   New primary metrics: error_rate={new_metrics['error_rate']:.2%}, "
                       f"priority_score={new_metrics['priority_score']}")

            # Source swap is logged at WARNING level — no need to flood Sentry with these.
            # Monitor via /api/v1/sources/health instead.

    def force_primary(self, source_url: str):
        """
        Manually force a specific source to be primary

        Args:
            source_url: URL to set as primary

        Raises:
            ValueError: If source_url is not in all_sources
        """
        if source_url not in self.all_sources:
            raise ValueError(f"Source {source_url} is not in configured sources")

        with self.manager_lock:
            old_primary = self.current_primary
            self.current_primary = source_url
            self.last_swap_time = datetime.utcnow()

            logger.warning(f"🔧 MANUALLY forced primary: {old_primary} → {source_url}")

    def reset_source_metrics(self, source_url: Optional[str] = None):
        """
        Reset metrics for a source (or all sources)

        Args:
            source_url: URL of source to reset, or None to reset all
        """
        if source_url:
            if source_url in self.source_metrics:
                self.source_metrics[source_url].reset_metrics()
            else:
                raise ValueError(f"Source {source_url} not found")
        else:
            # Reset all
            for metrics in self.source_metrics.values():
                metrics.reset_metrics()

            logger.info("🔄 All source metrics reset")


def get_source_manager() -> SourceManager:
    """
    Get singleton instance of SourceManager

    Thread-safe singleton pattern

    Returns:
        SourceManager: The singleton instance
    """
    global _source_manager_instance

    if _source_manager_instance is None:
        with _source_manager_lock:
            # Double-check locking
            if _source_manager_instance is None:
                _source_manager_instance = SourceManager()

    return _source_manager_instance


# Convenience function for testing
def reset_source_manager():
    """Reset the singleton instance (for testing)"""
    global _source_manager_instance
    with _source_manager_lock:
        _source_manager_instance = None
