let Audio = null;
try {
  Audio = require('expo-av').Audio;
} catch (e) {
  console.warn('expo-av not available, sounds disabled');
}

const SOUNDS = {
  coin: require('../../assets/coin.mp3'),
  notification: require('../../assets/notfication.mp3'),
};

class SoundManager {
  constructor() {
    this.sounds = {};
    this.isInitialized = false;
  }

  async initialize() {
    if (this.isInitialized || !Audio) return;
    
    try {
      await Audio.setAudioModeAsync({
        allowsRecordingIOS: false,
        staysActiveInBackground: false,
        playsInSilentModeIOS: true,
        shouldDuckAndroid: true,
        playThroughEarpieceAndroid: false,
      });
      
      for (const [key, source] of Object.entries(SOUNDS)) {
        const { sound } = await Audio.Sound.createAsync(source);
        this.sounds[key] = sound;
      }
      
      this.isInitialized = true;
    } catch (error) {
      console.warn('Sound initialization failed:', error);
    }
  }

  async playSound(soundName) {
    if (!Audio) return;
    if (!this.isInitialized) {
      await this.initialize();
    }
    
    try {
      const sound = this.sounds[soundName];
      if (sound) {
        await sound.replayAsync();
      }
    } catch (error) {
      console.warn(`Failed to play sound ${soundName}:`, error);
    }
  }

  async playNotificationSound() {
    await this.playSound('notification');
  }

  async playCoinSound() {
    await this.playSound('coin');
  }

  async cleanup() {
    for (const sound of Object.values(this.sounds)) {
      try { await sound.unloadAsync(); } catch {}
    }
    this.sounds = {};
    this.isInitialized = false;
  }
}

export default new SoundManager();
