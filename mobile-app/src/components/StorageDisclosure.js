import React from 'react';
import { View, Text, TouchableOpacity, Modal, StyleSheet } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

const StorageDisclosure = ({ visible, onAccept, onDecline }) => {
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
            <Ionicons name="folder" size={32} color="#8fc441" />
            <Text style={styles.title}>Storage Access Required</Text>
          </View>
          
          <Text style={styles.disclosureText}>
            FlipStar accesses device storage to save your created content and profile information for app functionality.
          </Text>
          
          <Text style={styles.usageTitle}>How we use storage access:</Text>
          <View style={styles.usageList}>
            <Text style={styles.usageItem}>• Save your created videos and photos</Text>
            <Text style={styles.usageItem}>• Store profile information</Text>
            <Text style={styles.usageItem}>• Cache content for offline viewing</Text>
            <Text style={styles.usageItem}>• Save app preferences and settings</Text>
          </View>
          
          <Text style={styles.privacyNote}>
            You can withdraw this consent at any time in your privacy settings.
          </Text>
          
          <View style={styles.buttonContainer}>
            <TouchableOpacity style={styles.declineButton} onPress={onDecline}>
              <Text style={styles.declineText}>Decline</Text>
            </TouchableOpacity>
            <TouchableOpacity style={styles.acceptButton} onPress={onAccept}>
              <Text style={styles.acceptText}>Allow Storage Access</Text>
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

export default StorageDisclosure;
