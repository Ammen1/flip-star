// Real-time post broadcasting service
// Uses BroadcastChannel API to notify all tabs/windows of new posts

class RealtimeService {
  constructor() {
    this.channel = null;
    this.listeners = new Map();
    this.init();
  }

  init() {
    try {
      // Create a broadcast channel for post updates
      this.channel = new BroadcastChannel('post_updates');
      
      // Listen for messages from other tabs
      this.channel.onmessage = (event) => {
        const { type, data } = event.data;
        this.notifyListeners(type, data);
      };
    } catch (error) {
      console.warn('BroadcastChannel not supported, falling back to localStorage:', error);
      this.initLocalStorageFallback();
    }
  }

  // Fallback for browsers that don't support BroadcastChannel
  initLocalStorageFallback() {
    window.addEventListener('storage', (event) => {
      if (event.key === 'post_update') {
        try {
          const { type, data } = JSON.parse(event.newValue);
          this.notifyListeners(type, data);
        } catch (error) {
          console.error('Failed to parse localStorage post update:', error);
        }
      }
    });
  }

  // Broadcast new post to all tabs
  broadcastNewPost(postData) {
    const message = {
      type: 'NEW_POST',
      data: {
        id: postData.id,
        user: postData.user,
        caption: postData.caption,
        media: postData.media || postData.image,
        created_at: postData.created_at,
        timestamp: Date.now()
      }
    };

    if (this.channel) {
      try {
        this.channel.postMessage(message);
      } catch (error) {
        console.error('Failed to broadcast post:', error);
        this.fallbackBroadcast(message);
      }
    } else {
      this.fallbackBroadcast(message);
    }
  }

  // Fallback using localStorage for cross-tab communication
  fallbackBroadcast(message) {
    try {
      localStorage.setItem('post_update', JSON.stringify(message));
      // Clear the message so it doesn't trigger multiple times
      setTimeout(() => {
        localStorage.removeItem('post_update');
      }, 100);
    } catch (error) {
      console.error('Failed to broadcast via localStorage:', error);
    }
  }

  // Add event listener for post updates
  addEventListener(type, callback) {
    if (!this.listeners.has(type)) {
      this.listeners.set(type, new Set());
    }
    this.listeners.get(type).add(callback);
  }

  // Remove event listener
  removeEventListener(type, callback) {
    if (this.listeners.has(type)) {
      this.listeners.get(type).delete(callback);
    }
  }

  // Notify all listeners of a specific event type
  notifyListeners(type, data) {
    if (this.listeners.has(type)) {
      this.listeners.get(type).forEach(callback => {
        try {
          callback(data);
        } catch (error) {
          console.error('Error in post update listener:', error);
        }
      });
    }
  }

  // Force refresh all feeds across all tabs
  broadcastFeedRefresh() {
    const message = {
      type: 'FEED_REFRESH',
      data: { timestamp: Date.now() }
    };

    if (this.channel) {
      try {
        this.channel.postMessage(message);
      } catch (error) {
        console.error('Failed to broadcast feed refresh:', error);
        this.fallbackBroadcast(message);
      }
    } else {
      this.fallbackBroadcast(message);
    }
  }

  // Clear all listeners
  cleanup() {
    this.listeners.clear();
    if (this.channel) {
      this.channel.close();
    }
  }
}

// Create singleton instance
const realtimeService = new RealtimeService();

export default realtimeService;




