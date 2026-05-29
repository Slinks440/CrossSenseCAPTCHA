package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"os"
	"os/signal"
	"strings"
	"sync"
	"syscall"
	"time"

	"github.com/confluentinc/confluent-kafka-go/v2/kafka"
	"github.com/go-redis/redis/v8"
)

type TelemetryEvent struct {
	ClientFp string `json:"client_fp"`
	IsBot    bool   `json:"is_bot"`
}

	redisDB    *redis.Client
	ctx        = context.Background()
)

// Removed getSubnet function

func main() {
	redisHost := os.Getenv("REDIS_HOST")
	if redisHost == "" {
		redisHost = "127.0.0.1:6379"
	}
	redisDB = redis.NewClient(&redis.Options{
		Addr: redisHost,
	})

	kafkaBroker := os.Getenv("KAFKA_BROKER")
	if kafkaBroker == "" {
		kafkaBroker = "localhost:9092"
	}

	c, err := kafka.NewConsumer(&kafka.ConfigMap{
		"bootstrap.servers": kafkaBroker,
		"group.id":          "captcha-telemetry-group",
		"auto.offset.reset": "latest",
	})
	if err != nil {
		log.Fatalf("Failed to create consumer: %s", err)
	}

	err = c.SubscribeTopics([]string{"captcha_telemetry"}, nil)
	if err != nil {
		log.Fatalf("Failed to subscribe: %s", err)
	}

	sigchan := make(chan os.Signal, 1)
	signal.Notify(sigchan, syscall.SIGINT, syscall.SIGTERM)

	// V14 Fix: Tumbling Window Ticker Removed.
	// We now use a pure Redis ZSET Sliding Window per event.

	run := true
	for run {
		select {
		case sig := <-sigchan:
			fmt.Printf("Caught signal %v: terminating\n", sig)
			run = false
		default:
			ev := c.Poll(100)
			if ev == nil {
				continue
			}

			switch e := ev.(type) {
			case *kafka.Message:
				key := string(e.Key)
				var data TelemetryEvent
				if err := json.Unmarshal(e.Value, &data); err != nil {
					continue
				}
				
				clientFp := data.ClientFp
				if clientFp == "" {
					continue
				}

				nowMs := time.Now().UnixNano() / int64(time.Millisecond)
				score := float64(nowMs)
				
				redisPoWKey := fmt.Sprintf("window_pow:%s", clientFp)
				redisVerifyKey := fmt.Sprintf("window_verify:%s", clientFp)
				
				pipe := redisDB.Pipeline()
				
				if key == "challenge_issued" {
					pipe.ZAdd(ctx, redisPoWKey, &redis.Z{Score: score, Member: nowMs})
				} else if key == "verification_attempt" && !data.IsBot {
					pipe.ZAdd(ctx, redisVerifyKey, &redis.Z{Score: score, Member: nowMs})
				}
				
				// Clean up old elements (older than 60s)
				cutoffScore := fmt.Sprintf("%f", float64(nowMs - 60000))
				pipe.ZRemRangeByScore(ctx, redisPoWKey, "-inf", cutoffScore)
				pipe.ZRemRangeByScore(ctx, redisVerifyKey, "-inf", cutoffScore)
				pipe.Expire(ctx, redisPoWKey, 65*time.Second)
				pipe.Expire(ctx, redisVerifyKey, 65*time.Second)
				
				powCountCmd := pipe.ZCount(ctx, redisPoWKey, "-inf", "+inf")
				verifyCountCmd := pipe.ZCount(ctx, redisVerifyKey, "-inf", "+inf")
				
				_, pipeErr := pipe.Exec(ctx)
				if pipeErr != nil {
					log.Printf("Redis pipeline err: %v", pipeErr)
					continue
				}
				
				powCount := powCountCmd.Val()
				verifyCount := verifyCountCmd.Val()
				
				if powCount >= 100 {
					conversion := float64(verifyCount) / float64(powCount)
					if conversion < 0.05 {
						log.Printf("Botnet detected on client_fp %s (PoW: %d, Solves: %d). Triggering Inflation.", clientFp, powCount, verifyCount)
						redisKey := fmt.Sprintf("client:%s:difficulty", clientFp)
						redisDB.Set(ctx, redisKey, 50, 3600*time.Second)
					}
				}

			case kafka.Error:
				fmt.Fprintf(os.Stderr, "%% Error: %v\n", e)
			}
		}
	}
	c.Close()
}
