// Simple global event emitter for campaign interactions
// This allows cross-screen communication for immediate leaderboard updates

const CampaignEventEmitter = {
  listeners: {},
  
  addListener(event, callback) {
    if (!this.listeners[event]) {
      this.listeners[event] = [];
    }
    this.listeners[event].push(callback);
    
    // Return unsubscribe function
    return () => {
      this.listeners[event] = this.listeners[event].filter(cb => cb !== callback);
    };
  },
  
  emit(event, data) {
    if (this.listeners[event]) {
      this.listeners[event].forEach(callback => {
        try {
          callback(data);
        } catch (error) {
          console.error('CampaignEventEmitter: Error in event callback:', error);
        }
      });
    }
  },
  
  // Remove all listeners for an event
  removeAllListeners(event) {
    if (this.listeners[event]) {
      this.listeners[event] = [];
    }
  },
  
  // Get the number of listeners for an event
  listenerCount(event) {
    return this.listeners[event] ? this.listeners[event].length : 0;
  }
};

export default CampaignEventEmitter;
