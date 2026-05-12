# Video Playback Issue - ReelsScreen

## Problem
Videos are not displaying in the ReelsScreen on mobile app.

## Root Cause
The expo-av Video component has a bug: "Error: Received 2 arguments, but 1 was expected"

This is a known issue with expo-av version incompatibility.

## What We Tried
1. ✅ WebView with HTML5 video - WebView doesn't render on Android
2. ✅ expo-av Video component - Has the "2 arguments" error
3. ✅ react-native-video - Package is broken (missing utils file)

## Solution Options

### Option 1: Update expo-av (RECOMMENDED)
```bash
cd flip/mobile-app
npx expo install expo-av@latest
```

### Option 2: Downgrade expo-av
```bash
cd flip/mobile-app
npm install expo-av@14.0.0
```

### Option 3: Use react-native-video (after fixing)
```bash
cd flip/mobile-app
npm install react-native-video@6.0.0
npx pod-install  # iOS only
```

## Current Status
- ✅ Login works (using /auth/login-with-phone/)
- ✅ Video URLs are correct and loading
- ✅ UI layout is correct
- ❌ Videos not displaying due to expo-av bug

## Files Modified
- `flip/mobile-app/src/screens/ReelsScreen.js` - Video component implementation
- `flip/mobile-app/src/screens/auth/LoginScreen.js` - Fixed login endpoint

## Next Steps
1. Update expo-av to latest version
2. Restart the app
3. Videos should work

## Note
The website uses HTML5 `<video>` tag which works in browsers. React Native apps need native video components (expo-av or react-native-video). This is a fundamental difference between web and mobile.
