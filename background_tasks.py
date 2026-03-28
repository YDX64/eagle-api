"""
Background Tasks - Cache Refresh & Cleanup
Kullanıcı fark etmeden arka planda cache'i fresh tutar

NOT: Gunicorn multi-worker ortamında sadece 1 worker background tasks çalıştırır.
Redis distributed lock ile leader election yapılır.
"""
import logging
import time
import threading
import os
from datetime import date, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

# ============================================================================
# LEADER ELECTION - Sadece 1 worker background tasks çalıştırsın
# ============================================================================
LEADER_LOCK_KEY = "golsinyali:background_tasks:leader"
LEADER_LOCK_TTL = 60  # 60 saniye - leader her 30 saniyede yeniler
LEADER_RENEW_INTERVAL = 30  # Lock'u 30 saniyede bir yenile

class BackgroundTaskManager:
    """
    Arka plan görevlerini yöneten manager.

    Görevler:
    1. Her 15 dakikada cache refresh (data fresh olsun) - DISABLED
    2. Her 1 saatte eski cache'leri temizle (disk şişmesin)
    3. Her 24 saatte log cleanup (log şişmesin)

    NOT: Multi-worker ortamında sadece 1 worker (leader) bu task'ları çalıştırır.
    Redis distributed lock ile leader election yapılır.
    """

    def __init__(self, cache_instance=None):
        self.cache = cache_instance
        self.running = False
        self.is_leader = False
        self.threads = []
        self.worker_id = f"worker-{os.getpid()}"
        self._redis_client = None

    def _get_redis_client(self):
        """Redis client'ı al (cache instance'dan)"""
        if self._redis_client is None and self.cache:
            try:
                # Flask-Caching'in Redis client'ını al
                self._redis_client = self.cache.cache._write_client
            except Exception as e:
                logger.warning(f"⚠️ Could not get Redis client: {e}")
        return self._redis_client

    def _try_acquire_leadership(self) -> bool:
        """
        Redis'te leader lock almaya çalış.
        SET NX (not exists) + EX (expire) ile atomic leader election.
        """
        redis_client = self._get_redis_client()
        if not redis_client:
            # Redis yoksa bu worker leader olsun (single worker mode)
            logger.warning("⚠️ Redis not available, assuming single worker mode")
            return True

        try:
            # SET key value NX EX ttl - atomic operation
            acquired = redis_client.set(
                LEADER_LOCK_KEY,
                self.worker_id,
                nx=True,  # Only set if not exists
                ex=LEADER_LOCK_TTL  # Expire in 60 seconds
            )

            if acquired:
                logger.info(f"👑 [{self.worker_id}] Acquired leadership for background tasks")
                return True
            else:
                # Başka worker leader - kim olduğunu logla
                current_leader = redis_client.get(LEADER_LOCK_KEY)
                if current_leader:
                    current_leader = current_leader.decode('utf-8') if isinstance(current_leader, bytes) else current_leader
                logger.info(f"⏸️ [{self.worker_id}] Another worker is leader: {current_leader}")
                return False

        except Exception as e:
            logger.error(f"❌ Leader election failed: {e}")
            return False

    def _renew_leadership(self) -> bool:
        """Leader lock'u yenile (TTL'i uzat)"""
        redis_client = self._get_redis_client()
        if not redis_client:
            return True

        try:
            # Sadece biz leader'sak yenile
            current_leader = redis_client.get(LEADER_LOCK_KEY)
            if current_leader:
                current_leader = current_leader.decode('utf-8') if isinstance(current_leader, bytes) else current_leader

            if current_leader == self.worker_id:
                redis_client.expire(LEADER_LOCK_KEY, LEADER_LOCK_TTL)
                return True
            else:
                logger.warning(f"⚠️ [{self.worker_id}] Lost leadership to {current_leader}")
                return False
        except Exception as e:
            logger.error(f"❌ Leadership renewal failed: {e}")
            return False

    def _release_leadership(self):
        """Leader lock'u serbest bırak"""
        redis_client = self._get_redis_client()
        if not redis_client:
            return

        try:
            # Sadece biz leader'sak sil
            current_leader = redis_client.get(LEADER_LOCK_KEY)
            if current_leader:
                current_leader = current_leader.decode('utf-8') if isinstance(current_leader, bytes) else current_leader

            if current_leader == self.worker_id:
                redis_client.delete(LEADER_LOCK_KEY)
                logger.info(f"👋 [{self.worker_id}] Released leadership")
        except Exception as e:
            logger.error(f"❌ Leadership release failed: {e}")

    def _leadership_renewal_loop(self):
        """Leader lock'u periyodik olarak yenile"""
        while self.running and self.is_leader:
            time.sleep(LEADER_RENEW_INTERVAL)
            if not self._renew_leadership():
                self.is_leader = False
                logger.warning(f"⚠️ [{self.worker_id}] Lost leadership, stopping tasks")
                break

    def start(self):
        """Tüm background task'ları başlat (sadece leader worker için)"""
        if self.running:
            logger.warning("Background tasks already running")
            return

        # Leader election - sadece 1 worker çalıştırsın
        self.is_leader = self._try_acquire_leadership()

        if not self.is_leader:
            logger.info(f"⏸️ [{self.worker_id}] Not leader, skipping background tasks")
            return

        self.running = True
        logger.info(f"🚀 [{self.worker_id}] Starting background tasks as LEADER...")

        # Task 1: Cache refresh - DISABLED (on-demand refresh kullanılacak)
        # Kullanıcı 30+ dakikalık cache'i talep edince arka planda refresh olacak
        # refresh_thread = threading.Thread(
        #     target=self._cache_refresh_loop,
        #     daemon=True,
        #     name="CacheRefreshThread"
        # )
        # refresh_thread.start()
        # self.threads.append(refresh_thread)
        logger.info("⏸️  Cache auto-refresh DISABLED (using on-demand refresh)")

        # Task 2: Cache cleanup (1 saatte bir)
        cleanup_thread = threading.Thread(
            target=self._cache_cleanup_loop,
            daemon=True,
            name="CacheCleanupThread"
        )
        cleanup_thread.start()
        self.threads.append(cleanup_thread)

        # Task 3: Log rotation (24 saatte bir)
        log_thread = threading.Thread(
            target=self._log_cleanup_loop,
            daemon=True,
            name="LogCleanupThread"
        )
        log_thread.start()
        self.threads.append(log_thread)

        # Task 4: Leadership renewal (leader lock'u periyodik yenile)
        renewal_thread = threading.Thread(
            target=self._leadership_renewal_loop,
            daemon=True,
            name="LeadershipRenewalThread"
        )
        renewal_thread.start()
        self.threads.append(renewal_thread)

        logger.info(f"✅ [{self.worker_id}] Started {len(self.threads)} background tasks as LEADER")

    def stop(self):
        """Background task'ları durdur ve leadership'i bırak"""
        logger.info(f"🛑 [{self.worker_id}] Stopping background tasks...")
        self.running = False

        # Thread'lerin durmasını bekle (max 5 saniye)
        for thread in self.threads:
            try:
                thread.join(timeout=5)
            except Exception as e:
                logger.warning(f"⚠️ Thread join failed: {e}")

        # Leadership'i serbest bırak
        if self.is_leader:
            self._release_leadership()
            self.is_leader = False

        self.threads = []
        logger.info(f"✅ [{self.worker_id}] Background tasks stopped")

    # ========================================================================
    # TASK 1: CACHE REFRESH (Her 15 dakikada bir)
    # ========================================================================
    def _cache_refresh_loop(self):
        """
        Her 15 dakikada bugünün maçlarını background'da refresh et.
        Kullanıcı fark etmez (async), data her zaman fresh.
        """
        logger.info("🔄 Cache refresh task started (15min interval)")

        while self.running:
            try:
                # İlk çalıştırmadan önce biraz bekle (startup'ta overload olmasın)
                time.sleep(60)  # 1 dakika bekle

                # Cache refresh yap
                self._refresh_today_matches()

                # 15 dakika bekle
                for _ in range(15 * 60):  # 15 dakika = 900 saniye
                    if not self.running:
                        break
                    time.sleep(1)

            except Exception as e:
                logger.error(f"❌ Cache refresh error: {e}", exc_info=True)
                time.sleep(60)  # Error durumunda 1 dakika bekle

        logger.info("🛑 Cache refresh task stopped")

    def _refresh_today_matches(self):
        """Bugünün tüm maçlarını background'da refresh et"""
        try:
            from routes.utils import fetch_date_matches_cached, fetch_match_data_with_analysis_cached

            today_str = date.today().strftime('%Y-%m-%d')
            logger.info(f"🔄 [BACKGROUND] Refreshing matches for {today_str}...")

            # Bugünün maçlarını al (cache bypass)
            matches_data = fetch_date_matches_cached(today_str, use_cache=False)

            if not matches_data or 'matches' not in matches_data:
                logger.warning(f"⚠️ [BACKGROUND] No matches found for {today_str}")
                return

            matches = matches_data['matches']
            match_count = len(matches)
            logger.info(f"🔄 [BACKGROUND] Found {match_count} matches to refresh")

            # Her maçı refresh et (rate limiting ile)
            refreshed = 0
            failed = 0

            for match in matches:
                if not self.running:
                    logger.info("🛑 [BACKGROUND] Refresh interrupted (shutdown)")
                    break

                try:
                    match_id = match.get('match_id')
                    if not match_id:
                        continue

                    # Background'da refresh (cache bypass)
                    fetch_match_data_with_analysis_cached(match_id, use_cache=False)
                    refreshed += 1

                    # Rate limiting (upstream'e yük binmesin)
                    time.sleep(0.5)  # 500ms bekle

                except Exception as e:
                    failed += 1
                    logger.warning(f"⚠️ [BACKGROUND] Failed to refresh match {match_id}: {e}")

            logger.info(
                f"✅ [BACKGROUND] Cache refresh completed: "
                f"{refreshed}/{match_count} refreshed, {failed} failed"
            )

        except Exception as e:
            logger.error(f"❌ [BACKGROUND] Refresh failed: {e}", exc_info=True)

    # ========================================================================
    # TASK 2: CACHE CLEANUP (Her 1 saatte bir)
    # ========================================================================
    def _cache_cleanup_loop(self):
        """
        Her 1 saatte eski cache'leri temizle.
        Disk şişmesin, sadece bugünün data'sı kalsın.
        """
        logger.info("🗑️ Cache cleanup task started (1 hour interval)")

        while self.running:
            try:
                # İlk çalıştırmadan önce 10 dakika bekle
                time.sleep(10 * 60)

                # Cleanup yap
                self._cleanup_old_cache()

                # 1 saat bekle
                for _ in range(60 * 60):  # 1 saat = 3600 saniye
                    if not self.running:
                        break
                    time.sleep(1)

            except Exception as e:
                logger.error(f"❌ Cache cleanup error: {e}", exc_info=True)
                time.sleep(60)

        logger.info("🛑 Cache cleanup task stopped")

    def _cleanup_old_cache(self):
        """Eski cache key'leri temizle (sadece bugünün data'sı kalsın)"""
        try:
            if not self.cache:
                logger.warning("⚠️ [CLEANUP] Cache instance not available")
                return

            logger.info("🗑️ [CLEANUP] Cleaning old cache entries...")

            # Redis'ten tüm key'leri al
            # NOT: Production'da scan() kullan (keys() blocking!)
            cache_backend = self.cache.cache._write_client

            today_str = date.today().strftime('%Y-%m-%d')
            yesterday_str = (date.today() - timedelta(days=1)).strftime('%Y-%m-%d')

            deleted_count = 0

            # Dünün ve önceki günlerin match cache'lerini sil
            for key in cache_backend.scan_iter(match='match_*'):
                try:
                    key_str = key.decode('utf-8') if isinstance(key, bytes) else key

                    # Bugünün ve dünün cache'i kalabilir (maçlar devam ediyor olabilir)
                    if today_str in key_str or yesterday_str in key_str:
                        continue

                    # Eski cache'i sil
                    cache_backend.delete(key)
                    deleted_count += 1

                except Exception as e:
                    logger.warning(f"⚠️ [CLEANUP] Failed to delete key {key}: {e}")

            logger.info(f"✅ [CLEANUP] Deleted {deleted_count} old cache entries")

        except Exception as e:
            logger.error(f"❌ [CLEANUP] Cleanup failed: {e}", exc_info=True)

    # ========================================================================
    # TASK 3: LOG CLEANUP (Her 24 saatte bir)
    # ========================================================================
    def _log_cleanup_loop(self):
        """
        Her 24 saatte log dosyalarını temizle.
        Sadece son 7 günün log'u kalsın.
        """
        logger.info("📋 Log cleanup task started (24 hour interval)")

        while self.running:
            try:
                # İlk çalıştırmadan önce 1 saat bekle
                time.sleep(60 * 60)

                # Cleanup yap
                self._cleanup_old_logs()

                # 24 saat bekle
                for _ in range(24 * 60 * 60):  # 24 saat
                    if not self.running:
                        break
                    time.sleep(1)

            except Exception as e:
                logger.error(f"❌ Log cleanup error: {e}", exc_info=True)
                time.sleep(60)

        logger.info("🛑 Log cleanup task stopped")

    def _cleanup_old_logs(self):
        """7 günden eski log dosyalarını sil"""
        try:
            import os
            import glob

            logger.info("📋 [CLEANUP] Cleaning old log files...")

            log_dir = 'logs'
            if not os.path.exists(log_dir):
                return

            # 7 gün önce
            cutoff_time = time.time() - (7 * 24 * 60 * 60)
            deleted_count = 0
            total_size_freed = 0

            # Tüm .log dosyalarını kontrol et
            for log_file in glob.glob(os.path.join(log_dir, '*.log*')):
                try:
                    # app.log'u silme (active log)
                    if log_file.endswith('app.log'):
                        continue

                    # Dosya yaşını kontrol et
                    file_mtime = os.path.getmtime(log_file)

                    if file_mtime < cutoff_time:
                        file_size = os.path.getsize(log_file)
                        os.remove(log_file)
                        deleted_count += 1
                        total_size_freed += file_size
                        logger.debug(f"🗑️ Deleted old log: {log_file}")

                except Exception as e:
                    logger.warning(f"⚠️ [CLEANUP] Failed to delete log {log_file}: {e}")

            if deleted_count > 0:
                size_mb = total_size_freed / (1024 * 1024)
                logger.info(
                    f"✅ [CLEANUP] Deleted {deleted_count} old log files "
                    f"({size_mb:.2f} MB freed)"
                )
            else:
                logger.info("✅ [CLEANUP] No old log files to delete")

        except Exception as e:
            logger.error(f"❌ [CLEANUP] Log cleanup failed: {e}", exc_info=True)


# Global instance (app.py'dan erişim için)
_task_manager: Optional[BackgroundTaskManager] = None

def init_background_tasks(cache_instance):
    """Background task manager'ı başlat"""
    global _task_manager

    if _task_manager is not None:
        logger.warning("Background tasks already initialized")
        return _task_manager

    _task_manager = BackgroundTaskManager(cache_instance)
    _task_manager.start()

    return _task_manager

def get_task_manager() -> Optional[BackgroundTaskManager]:
    """Mevcut task manager'ı al"""
    return _task_manager

def get_background_tasks_status() -> dict:
    """Background tasks durumunu al (health check için)"""
    if _task_manager is None:
        return {
            "initialized": False,
            "is_leader": False,
            "worker_id": f"worker-{os.getpid()}",
            "running": False,
            "thread_count": 0
        }

    return {
        "initialized": True,
        "is_leader": _task_manager.is_leader,
        "worker_id": _task_manager.worker_id,
        "running": _task_manager.running,
        "thread_count": len(_task_manager.threads)
    }

def stop_background_tasks():
    """Background task'ları durdur"""
    global _task_manager

    if _task_manager:
        _task_manager.stop()
        _task_manager = None
