#!/bin/bash
# Monitor PDF service on shared MongoDB VM
# Usage: ./monitor_shared_vm.sh

set -e

ALERT_MEMORY=3200  # 80% of 4GB
ALERT_CPU=75
MONGODB_PORT=27017
PDF_API_PORT=8000

clear

while true; do
    clear

    echo "==================================="
    echo "PDF Service Monitor (Shared VM)"
    echo "==================================="
    echo "Time: $(date '+%Y-%m-%d %H:%M:%S')"
    echo ""

    # Memory Status
    echo "📊 MEMORY STATUS"
    MEMORY_FREE=$(free -m | awk 'NR==2{print $7}')
    MEMORY_USED=$(free -m | awk 'NR==2{print $3}')
    MEMORY_TOTAL=$(free -m | awk 'NR==2{print $2}')
    MEMORY_PERCENT=$((MEMORY_USED * 100 / MEMORY_TOTAL))

    if [ $MEMORY_USED -gt $ALERT_MEMORY ]; then
        echo "⚠️  Memory: ${MEMORY_USED}MB / ${MEMORY_TOTAL}MB (${MEMORY_PERCENT}%) [ALERT]"
    else
        echo "✅ Memory: ${MEMORY_USED}MB / ${MEMORY_TOTAL}MB (${MEMORY_PERCENT}%)"
    fi
    echo ""

    # CPU Status
    echo "💻 CPU STATUS"
    CPU_USAGE=$(top -bn1 | grep "Cpu(s)" | awk '{print $2}' | sed 's/%us,//' | cut -d'.' -f1)

    if [ "$CPU_USAGE" -gt "$ALERT_CPU" ]; then
        echo "⚠️  CPU: ${CPU_USAGE}% [ALERT]"
    else
        echo "✅ CPU: ${CPU_USAGE}%"
    fi
    echo ""

    # Process Status
    echo "🔧 PROCESS STATUS"

    MONGODB=$(pgrep -f mongod | wc -l)
    if [ "$MONGODB" -gt 0 ]; then
        echo "✅ MongoDB: Running"
        MONGODB_MEMORY=$(ps aux | grep mongod | grep -v grep | awk '{print $6}' | head -1)
        echo "   Memory: ${MONGODB_MEMORY}KB"
    else
        echo "❌ MongoDB: NOT RUNNING"
    fi

    FASTAPI=$(pgrep -f "uvicorn" | wc -l)
    if [ "$FASTAPI" -gt 0 ]; then
        echo "✅ FastAPI: Running"
        FASTAPI_MEMORY=$(ps aux | grep uvicorn | grep -v grep | awk '{print $6}' | head -1)
        echo "   Memory: ${FASTAPI_MEMORY}KB"
    else
        echo "❌ FastAPI: NOT RUNNING"
    fi

    WORKERS=$(pgrep -f "worker.py" | wc -l)
    echo "✅ Workers: $WORKERS running"
    if [ "$WORKERS" -gt 0 ]; then
        WORKER_MEMORY=$(ps aux | grep worker.py | grep -v grep | awk '{sum+=$6} END {print sum}')
        echo "   Total Memory: ${WORKER_MEMORY}KB"
    fi
    echo ""

    # Database Status
    echo "🗄️  DATABASE STATUS"

    # MongoDB connections
    MONGO_CONN=$(echo "db.serverStatus().connections" | mongosh --quiet 2>/dev/null | grep "current" | grep -o "[0-9]*" | head -1)
    if [ -z "$MONGO_CONN" ]; then
        MONGO_CONN="?"
    fi
    echo "✅ MongoDB Connections: $MONGO_CONN"

    # Redis connections
    REDIS_CONN=$(redis-cli info stats 2>/dev/null | grep "connected_clients" | cut -d':' -f2 | tr -d '\r')
    if [ -z "$REDIS_CONN" ]; then
        REDIS_CONN="?"
    fi
    echo "✅ Redis Connections: $REDIS_CONN"
    echo ""

    # Queue Status
    echo "📋 QUEUE STATUS"
    QUEUE_STATS=$(curl -s http://localhost:${PDF_API_PORT}/api/v1/pdf/sign-async/stats 2>/dev/null)

    if [ -n "$QUEUE_STATS" ]; then
        QUEUED=$(echo "$QUEUE_STATS" | grep -o '"queued":[0-9]*' | cut -d':' -f2)
        PROCESSING=$(echo "$QUEUE_STATS" | grep -o '"processing":[0-9]*' | cut -d':' -f2)
        COMPLETED=$(echo "$QUEUE_STATS" | grep -o '"completed_today":[0-9]*' | cut -d':' -f2)

        echo "✅ Queued: $QUEUED"
        echo "✅ Processing: $PROCESSING"
        echo "✅ Completed today: $COMPLETED"
    else
        echo "❌ Cannot reach API"
    fi
    echo ""

    # Recommendations
    echo "💡 RECOMMENDATIONS"
    if [ $MEMORY_PERCENT -gt 80 ]; then
        echo "⚠️  Memory high - Consider restarting workers"
    fi
    if [ "$CPU_USAGE" -gt 75 ]; then
        echo "⚠️  CPU high - May need to reduce worker concurrency"
    fi
    if [ "$QUEUED" -gt 500 ]; then
        echo "⚠️  Queue building up - May need more workers"
    fi
    if [ "$QUEUED" -lt 5 ] && [ "$CPU_USAGE" -lt 30 ]; then
        echo "✅ System running optimally"
    fi
    echo ""

    # Footer
    echo "==================================="
    echo "Refreshing in 10 seconds... (Ctrl+C to stop)"
    echo "==================================="

    sleep 10
done
