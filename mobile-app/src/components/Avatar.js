import React, { useState } from 'react';
import { View, Text, Image } from 'react-native';
import config from '../config';

const GOLD = '#C8B56A';

const Avatar = React.memo(({ uri, size = 36, name = '' }) => {
  const [err, setErr] = useState(false);
  const safeName = name || '?';
  
  // Normalize URI - handle both relative and absolute URLs
  let normalizedUri = uri;
  if (uri && !uri.startsWith('http')) {
    // If it's a relative path, prepend the API base URL (without /api)
    const baseUrl = config.API_BASE_URL.replace('/api', '');
    normalizedUri = uri.startsWith('/') ? `${baseUrl}${uri}` : `${baseUrl}/${uri}`;
  }
  
  if (normalizedUri && !err) {
    return (
      <Image 
        source={{ uri: normalizedUri }} 
        style={{ width: size, height: size, borderRadius: size / 2 }} 
        onError={(e) => {
          console.log('Avatar load error:', { original: uri, normalized: normalizedUri, name, error: e.nativeEvent });
          setErr(true);
        }} 
      />
    );
  }
  return (
    <View style={{ width: size, height: size, borderRadius: size / 2, backgroundColor: GOLD, justifyContent: 'center', alignItems: 'center' }}>
      <Text style={{ color: '#000', fontWeight: '700', fontSize: size * 0.4 }}>{safeName[0].toUpperCase()}</Text>
    </View>
  );
});

export default Avatar;
