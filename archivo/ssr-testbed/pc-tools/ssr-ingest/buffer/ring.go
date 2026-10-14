package buffer

import (
	"sync"
	"time"
)

type Ring struct {
	mu       sync.RWMutex
	buf      []interface{}
	head     int
	tail     int
	count    int
	capacity int
	duration time.Duration
}

func NewRing(duration time.Duration) *Ring {
	cap := int(duration.Seconds() * 2000)
	if cap < 100 {
		cap = 100
	}
	return &Ring{
		buf:      make([]interface{}, cap),
		capacity: cap,
		duration: duration,
	}
}

func (r *Ring) Push(item interface{}) bool {
	r.mu.Lock()
	defer r.mu.Unlock()

	if r.count == r.capacity {
		return false
	}

	r.buf[r.tail] = item
	r.tail = (r.tail + 1) % r.capacity
	r.count++
	return true
}

func (r *Ring) Pop() interface{} {
	r.mu.Lock()
	defer r.mu.Unlock()

	if r.count == 0 {
		return nil
	}

	item := r.buf[r.head]
	r.buf[r.head] = nil
	r.head = (r.head + 1) % r.capacity
	r.count--
	return item
}

func (r *Ring) Peek(n int) []interface{} {
	r.mu.RLock()
	defer r.mu.RUnlock()

	if n > r.count {
		n = r.count
	}

	result := make([]interface{}, n)
	idx := r.head
	for i := 0; i < n; i++ {
		result[i] = r.buf[idx]
		idx = (idx + 1) % r.capacity
	}
	return result
}

func (r *Ring) Len() int {
	r.mu.RLock()
	defer r.mu.RUnlock()
	return r.count
}

func (r *Ring) Cap() int {
	return r.capacity
}
