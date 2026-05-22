import React from 'react';
import { View, Text, TouchableOpacity, Modal, StyleSheet } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

const CameraDisclosure = ({ visible, onAccept, onDecline }) => {
  return (
    <Modal
      visible={visible}
      transparent={true}
      animationType="fade"
      onRequestClose={onDecline}
    >
      <View style={styles.overlay}>
        <View style={styles.disclosureContainer}>
          <View style={styles.header}>
            <Ionicons name="camera" size={32} color="#8fc441" />
            <Text style={styles.title}>Camera Access Required</Text>
          </View>
          
          <Text style={styles.disclosureText}>
            FlipStar collects camera data to enable video and photo creation for social content sharing and campaign participation.
          </Text>
          
          <Text style={styles.usageTitle}>How we use your camera data:</Text>
          <View style={styles.usageList}>
            <Text style={styles.usageItem}>• Create and share videos and photos</Text>
            <Text style={styles.usageItem}>• Participate in campaigns</Text>
            <Text style={styles.usageItem}>• Set profile pictures</Text>
            <Text style={styles.usageItem}>• Record content for social interaction</Text>
          </View>
          
          <Text style={styles.privacyNote}>
            You can withdraw this consent at any time in your privacy settings.
          </Text>
          
          <View style={styles.buttonContainer}>
            <TouchableOpacity style={styles.declineButton} onPress={onDecline}>
              <Text style={styles.declineText}>Decline</Text>
            </TouchableOpacity>
            <TouchableOpacity style={styles.acceptButton} onPress={onAccept}>
              <Text style={styles.acceptText}>Allow Camera Access</Text>
            </TouchableOpacity>
          </View>
        </View>
      </View>
    </Modal>
  );
};

const styles = StyleSheet.create({
  overlay: {
    flex: 1,
    backgroundColor: 'rgba(0, 0, 0, 0.5)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  disclosureContainer: {
    backgroundColor: '#1A1A1A',
    borderRadius: 16,
    padding: 24,
    margin: 20,
    maxWidth: 400,
    width: '100%',
  },
  header: {
    alignItems: 'center',
    marginBottom: 20,
  },
  title: {
    color: '#fff',
    fontSize: 20,
    fontWeight: 'bold',
    marginTop: 12,
    textAlign: 'center',
  },
  disclosureText: {
    color: '#ccc',
    fontSize: 16,
    lineHeight: 24,
    marginBottom: 20,
    textAlign: 'center',
  },
  usageTitle: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
    marginBottom: 12,
  },
  usageList: {
    marginBottom: 20,
  },
  usageItem: {
    color: '#ccc',
    fontSize: 14,
    lineHeight: 20,
    marginBottom: 4,
  },
  privacyNote: {
    color: '#888',
    fontSize: 12,
    fontStyle: 'italic',
    marginBottom: 24,
    textAlign: 'center',
  },
  buttonContainer: {
    flexDirection: 'row',
    gap: 12,
  },
  declineButton: {
    flex: 1,
    backgroundColor: '#333',
    paddingVertical: 12,
    paddingHorizontal: 20,
    borderRadius: 8,
    alignItems: 'center',
  },
  declineText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
  },
  acceptButton: {
    flex: 1,
    backgroundColor: '#8fc441',
    paddingVertical: 12,
    paddingHorizontal: 20,
    borderRadius: 8,
    alignItems: 'center',
  },
  acceptText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
  },
});

export default CameraDisclosure;
