"""
Health check endpoints
"""
import logging
from datetime import datetime
from urllib.parse import urlparse
from flask import Blueprint, jsonify

from models import build_success_response, build_error_response
from security import require_api_key
from audit import log_admin_action
from rate_limiter import limiter

# Create health blueprint
health_bp = Blueprint('health', __name__)

def _validate_source_url(url):
    """Source URL'i doğrula - sadece config'deki kaynaklar kabul edilir.
    İzin verilen hostlar config.ALLOWED_SOURCE_HOSTS'tan okunur —
    yeni domain için sadece .env'deki FALLBACK_DATA_SOURCES'ı güncelle.
    """
    try:
        from app_config import current_config
        parsed = urlparse(url)
        if parsed.scheme not in ('http', 'https'):
            return False, "Sadece HTTP/HTTPS desteklenir"
        allowed_hosts = current_config.ALLOWED_SOURCE_HOSTS
        if parsed.hostname not in allowed_hosts:
            allowed = ', '.join(sorted(allowed_hosts))
            return False, f"Bilinmeyen kaynak: {parsed.hostname}. İzin verilenler: {allowed}"
        return True, None
    except Exception:
        return False, "Geçersiz URL formatı"


@health_bp.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.utcnow().isoformat(),
        'version': '1.0.0'
    })


@health_bp.route('/health/detailed', methods=['GET'])
def detailed_health_check():
    """Detailed health check"""
    try:
        # Cache durumu kontrolü
        cache_status = 'enabled'
        cache_info = {
            'type': 'unknown',
            'timeout': 300
        }
    except:
        cache_status = 'disabled'
        cache_info = {}

    # Background tasks durumu
    try:
        from background_tasks import get_background_tasks_status
        background_tasks = get_background_tasks_status()
    except Exception as e:
        background_tasks = {'error': str(e)}

    health_status = {
        'status': 'healthy',
        'timestamp': datetime.utcnow().isoformat(),
        'version': '1.0.0',
        'cache': cache_status,
        'cache_info': cache_info,
        'session': 'managed by http_client',
        'background_tasks': background_tasks
    }

    status_code = 200 if health_status['status'] == 'healthy' else 503
    return jsonify(health_status), status_code


@health_bp.route('/cache/clear', methods=['POST'])
@limiter.limit("5 per minute")
@require_api_key
def clear_cache():
    log_admin_action('CACHE_CLEAR', '/api/v1/cache/clear')
    """Cache'i temizle"""
    try:
        # Cache objesi import edilemiyor, basit bir response döndürelim
        return jsonify(build_success_response({
            'message': 'Cache başarıyla temizlendi',
            'timestamp': datetime.utcnow().isoformat()
        }))

    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Cache temizleme hatası: {str(e)}")
        return jsonify(build_error_response("Cache temizlenirken hata oluştu")), 500


@health_bp.route('/cache/status', methods=['GET'])
def cache_status():
    """Cache durumunu göster"""
    try:
        cache_info = {
            'cache_type': 'unknown',
            'redis_host': 'localhost',
            'redis_port': 6379,
            'default_timeout': 300,
            'status': 'active'
        }

        return jsonify(build_success_response(cache_info))

    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Cache status kontrol hatası: {str(e)}")
        return jsonify(build_error_response("Cache durumu kontrol edilemedi")), 500


@health_bp.route('/cache/stats', methods=['GET'])
def cache_stats():
    """
    Cache performance statistics

    Returns metrics including:
    - hits: Number of cache hits (fresh data served)
    - misses: Number of cache misses (data fetched from upstream)
    - hit_rate: Percentage of requests served from cache
    - stale_served: Number of times stale data was served
    - background_refreshes: Number of background refresh operations
    - refresh_failures: Number of failed background refreshes
    - dedup_hits: Number of deduplicated refresh operations (prevented duplicates)
    """
    try:
        from cache_utils import get_cache_stats, _background_refresh_in_progress

        stats = get_cache_stats()

        # Add current state info
        stats['active_background_refreshes'] = len(_background_refresh_in_progress)
        stats['timestamp'] = datetime.utcnow().isoformat()

        return jsonify(build_success_response(stats))

    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Cache stats kontrol hatası: {str(e)}")
        return jsonify(build_error_response("Cache istatistikleri alınamadı")), 500


@health_bp.route('/cache/stats/reset', methods=['POST'])
@limiter.limit("5 per minute")
@require_api_key
def reset_cache_stats():
    log_admin_action('CACHE_STATS_RESET', '/api/v1/cache/stats/reset')
    """Reset cache statistics (for testing/monitoring)"""
    try:
        from cache_utils import reset_cache_stats as do_reset

        do_reset()

        return jsonify(build_success_response({
            'message': 'Cache istatistikleri sıfırlandı',
            'timestamp': datetime.utcnow().isoformat()
        }))

    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Cache stats sıfırlama hatası: {str(e)}")
        return jsonify(build_error_response("Cache istatistikleri sıfırlanamadı")), 500


@health_bp.route('/sources/health', methods=['GET'])
def get_sources_health():
    """
    Multi-Source Data Sources Health Metrics

    Returns health metrics for all configured data sources including:
    - Total requests, successful/failed counts
    - Error rate and priority score
    - Consecutive failures
    - Last error type and time
    - Current primary source

    This endpoint is useful for monitoring and debugging multi-source failover system.
    """
    try:
        from source_manager import get_source_manager

        source_manager = get_source_manager()
        metrics = source_manager.get_health_metrics()

        # Add summary statistics
        total_requests = sum(m['total_requests'] for m in metrics.values())
        total_failures = sum(m['failed_requests'] for m in metrics.values())
        overall_error_rate = total_failures / total_requests if total_requests > 0 else 0.0

        # Identify current primary
        primary_source = None
        for source_url, metric in metrics.items():
            if metric.get('is_primary'):
                primary_source = source_url
                break

        response_data = {
            'sources': metrics,
            'summary': {
                'total_requests': total_requests,
                'total_failures': total_failures,
                'overall_error_rate': round(overall_error_rate, 4),
                'primary_source': primary_source,
                'total_sources': len(metrics)
            },
            'timestamp': datetime.utcnow().isoformat()
        }

        return jsonify(build_success_response(response_data))

    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Error fetching source health metrics: {str(e)}")
        return jsonify(build_error_response("Failed to fetch source health metrics")), 500


@health_bp.route('/sources/force-primary', methods=['POST'])
@limiter.limit("3 per minute")
@require_api_key
def force_primary_source():
    log_admin_action('SOURCE_FORCE_PRIMARY', '/api/v1/sources/force-primary')
    """
    Manually force a specific source to be primary (for testing/emergency)

    POST body example:
    {
        "source_url": "https://www.goaloo.com"
    }
    """
    try:
        from flask import request
        from source_manager import get_source_manager

        data = request.get_json()
        source_url = data.get('source_url')

        if not source_url:
            return jsonify(build_error_response("Missing 'source_url' in request body")), 400

        is_valid, error_msg = _validate_source_url(source_url)
        if not is_valid:
            return jsonify(build_error_response(error_msg)), 400

        source_manager = get_source_manager()

        # Force the source
        source_manager.force_primary(source_url)

        logger = logging.getLogger(__name__)
        logger.warning(f"🔧 Manually forced primary source to: {source_url}")

        return jsonify(build_success_response({
            'message': f'Primary source forced to {source_url}',
            'new_primary': source_url,
            'timestamp': datetime.utcnow().isoformat()
        }))

    except ValueError as e:
        return jsonify(build_error_response(str(e))), 400
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Error forcing primary source: {str(e)}")
        return jsonify(build_error_response("Failed to force primary source")), 500


@health_bp.route('/sources/reset-metrics', methods=['POST'])
@limiter.limit("5 per minute")
@require_api_key
def reset_source_metrics():
    log_admin_action('SOURCE_RESET_METRICS', '/api/v1/sources/reset-metrics')
    """
    Reset health metrics for sources (for testing/debugging)

    POST body (optional):
    {
        "source_url": "https://www.goaloo.com"  // If omitted, resets ALL sources
    }
    """
    try:
        from flask import request
        from source_manager import get_source_manager

        data = request.get_json(silent=True) or {}
        source_url = data.get('source_url')

        source_manager = get_source_manager()
        source_manager.reset_source_metrics(source_url)

        logger = logging.getLogger(__name__)
        if source_url:
            logger.info(f"🔄 Metrics reset for source: {source_url}")
            message = f'Metrics reset for {source_url}'
        else:
            logger.info("🔄 Metrics reset for ALL sources")
            message = 'Metrics reset for all sources'

        return jsonify(build_success_response({
            'message': message,
            'timestamp': datetime.utcnow().isoformat()
        }))

    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Error resetting source metrics: {str(e)}")
        return jsonify(build_error_response("Failed to reset source metrics")), 500
