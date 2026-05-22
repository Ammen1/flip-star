import React from 'react';
import { View, Text, TouchableOpacity, ScrollView, StyleSheet, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useConsent } from '../contexts/ConsentContext';

const ConsentDashboard = ({ navigation }) => {
  const { consents, consentHistory, updateConsent, withdrawConsent, hasConsent, loading, getConsentSummary } = useConsent();

  if (loading) {
    return (
      <View style={styles.loadingContainer}>
        <ActivityIndicator size="large" color="#8fc441" />
        <Text style={styles.loadingText}>Loading privacy settings...</Text>
      </View>
    );
  }

  const consentItems = [
    {
      key: 'camera',
      title: 'Camera Access',
      description: 'Allow app to access camera for creating content',
      icon: 'camera',
      required: false,
      color: '#8fc441'
    },
    {
      key: 'storage',
      title: 'Storage Access',
      description: 'Allow app to access device storage for saving content',
      icon: 'folder',
      required: false,
      color: '#8fc441'
    },
    {
      key: 'analytics',
      title: 'Analytics Data',
      description: 'Help us improve the app by sharing usage analytics',
      icon: 'analytics',
      required: false,
      color: '#8fc441'
    },
    {
      key: 'marketing',
      title: 'Marketing Communications',
      description: 'Receive updates about new features and promotions',
      icon: 'mail',
      required: false,
      color: '#8fc441'
    },
    {
      key: 'functional',
      title: 'Functional Data',
      description: 'Essential data for app functionality (cannot be disabled)',
      icon: 'settings',
      required: true,
      color: '#6B7280'
    },
    {
      key: 'necessary',
      title: 'Necessary Data',
      description: 'Required for basic app operation (cannot be disabled)',
      icon: 'lock-closed',
      required: true,
      color: '#6B7280'
    }
  ];

  const summary = getConsentSummary();

  return (
    <ScrollView style={styles.container}>
      <View style={styles.header}>
        <Ionicons name="shield-checkmark" size={48} color="#3B82F6" />
        <Text style={styles.title}>Privacy Settings</Text>
        <Text style={styles.subtitle}>Manage your data sharing preferences</Text>
      </View>

      <View style={styles.summaryCard}>
        <Text style={styles.summaryTitle}>Consent Summary</Text>
        <View style={styles.summaryRow}>
          <Text style={styles.summaryText}>Total Consents: {summary.totalConsents}</Text>
          <Text style={styles.summaryText}>Granted: {summary.grantedConsents}</Text>
        </View>
        {summary.lastUpdated && (
          <Text style={styles.lastUpdated}>
            Last updated: {new Date(summary.lastUpdated).toLocaleDateString()}
          </Text>
        )}
      </View>

      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Data Permissions</Text>
        {consentItems.map(item => (
          <View key={item.key} style={styles.consentItem}>
            <View style={styles.consentInfo}>
              <View style={[styles.iconContainer, { backgroundColor: item.color + '20' }]}>
                <Ionicons name={item.icon} size={24} color={item.color} />
              </View>
              <View style={styles.consentText}>
                <Text style={styles.consentTitle}>{item.title}</Text>
                <Text style={styles.consentDescription}>{item.description}</Text>
              </View>
            </View>
            {item.required ? (
              <View style={styles.requiredBadge}>
                <Text style={styles.requiredText}>Required</Text>
              </View>
            ) : (
              <TouchableOpacity
                style={[styles.toggleButton, consents[item.key] && styles.toggleButtonActive]}
                onPress={() => updateConsent(item.key, !consents[item.key])}
              >
                <Text style={styles.toggleText}>
                  {consents[item.key] ? 'ON' : 'OFF'}
                </Text>
              </TouchableOpacity>
            )}
          </View>
        ))}
      </View>

      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Consent History</Text>
        {consentHistory.length === 0 ? (
          <Text style={styles.noHistoryText}>No consent changes recorded</Text>
        ) : (
          consentHistory.slice(-5).reverse().map((entry, index) => (
            <View key={index} style={styles.historyItem}>
              <View style={styles.historyContent}>
                <Text style={styles.historyText}>
                  {entry.type.charAt(0).toUpperCase() + entry.type.slice(1)} - {entry.granted ? 'Granted' : 'Withdrawn'}
                </Text>
                <Text style={styles.historyDate}>
                  {new Date(entry.timestamp).toLocaleDateString()} {new Date(entry.timestamp).toLocaleTimeString()}
                </Text>
              </View>
              <View style={[styles.historyIndicator, { backgroundColor: entry.granted ? '#10B981' : '#EF4444' }]}>
                <Ionicons 
                  name={entry.granted ? 'checkmark' : 'close'} 
                  size={16} 
                  color="#fff" 
                />
              </View>
            </View>
          ))
        )}
      </View>

      <TouchableOpacity 
        style={styles.exportButton}
        onPress={() => navigation.navigate('DataExport')}
      >
        <Ionicons name="download" size={20} color="#fff" />
        <Text style={styles.exportButtonText}>Export My Data</Text>
      </TouchableOpacity>

      <TouchableOpacity 
        style={styles.policyButton}
        onPress={() => navigation.navigate('PrivacyPolicy')}
      >
        <Ionicons name="document-text" size={20} color="#3B82F6" />
        <Text style={styles.policyButtonText}>View Privacy Policy</Text>
      </TouchableOpacity>

      <TouchableOpacity 
        style={styles.euRightsButton}
        onPress={() => navigation.navigate('EURights')}
      >
        <Ionicons name="balance" size={20} color="#8B5CF6" />
        <Text style={styles.euRightsButtonText}>EU Privacy Rights</Text>
      </TouchableOpacity>
    </ScrollView>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#0D0D0D',
  },
  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: '#0D0D0D',
  },
  loadingText: {
    color: '#fff',
    marginTop: 16,
    fontSize: 16,
  },
  header: {
    alignItems: 'center',
    padding: 24,
    paddingTop: 60,
  },
  title: {
    color: '#fff',
    fontSize: 28,
    fontWeight: 'bold',
    marginTop: 16,
  },
  subtitle: {
    color: '#888',
    fontSize: 16,
    marginTop: 8,
    textAlign: 'center',
  },
  summaryCard: {
    backgroundColor: '#1A1A1A',
    margin: 20,
    padding: 20,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: '#262626',
  },
  summaryTitle: {
    color: '#fff',
    fontSize: 18,
    fontWeight: '600',
    marginBottom: 12,
  },
  summaryRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 8,
  },
  summaryText: {
    color: '#ccc',
    fontSize: 14,
  },
  lastUpdated: {
    color: '#888',
    fontSize: 12,
    fontStyle: 'italic',
  },
  section: {
    margin: 20,
    marginTop: 0,
  },
  sectionTitle: {
    color: '#fff',
    fontSize: 20,
    fontWeight: '600',
    marginBottom: 16,
  },
  consentItem: {
    backgroundColor: '#1A1A1A',
    padding: 16,
    borderRadius: 12,
    marginBottom: 12,
    borderWidth: 1,
    borderColor: '#262626',
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  consentInfo: {
    flexDirection: 'row',
    alignItems: 'center',
    flex: 1,
  },
  iconContainer: {
    width: 48,
    height: 48,
    borderRadius: 24,
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 16,
  },
  consentText: {
    flex: 1,
  },
  consentTitle: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
    marginBottom: 4,
  },
  consentDescription: {
    color: '#888',
    fontSize: 14,
    lineHeight: 20,
  },
  requiredBadge: {
    backgroundColor: '#6B7280',
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 6,
  },
  requiredText: {
    color: '#fff',
    fontSize: 12,
    fontWeight: '600',
  },
  toggleButton: {
    backgroundColor: '#333',
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderRadius: 20,
    minWidth: 60,
    alignItems: 'center',
  },
  toggleButtonActive: {
    backgroundColor: '#3B82F6',
  },
  toggleText: {
    color: '#fff',
    fontSize: 12,
    fontWeight: '600',
  },
  noHistoryText: {
    color: '#888',
    fontSize: 14,
    fontStyle: 'italic',
    textAlign: 'center',
    padding: 20,
  },
  historyItem: {
    backgroundColor: '#1A1A1A',
    padding: 16,
    borderRadius: 12,
    marginBottom: 8,
    borderWidth: 1,
    borderColor: '#262626',
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  historyContent: {
    flex: 1,
  },
  historyText: {
    color: '#fff',
    fontSize: 14,
    fontWeight: '500',
  },
  historyDate: {
    color: '#888',
    fontSize: 12,
    marginTop: 4,
  },
  historyIndicator: {
    width: 32,
    height: 32,
    borderRadius: 16,
    justifyContent: 'center',
    alignItems: 'center',
    marginLeft: 12,
  },
  exportButton: {
    backgroundColor: '#3B82F6',
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    padding: 16,
    margin: 20,
    borderRadius: 12,
    gap: 8,
  },
  exportButtonText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
  },
  policyButton: {
    backgroundColor: '#1A1A1A',
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    padding: 16,
    margin: 20,
    marginTop: 0,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: '#3B82F6',
    gap: 8,
  },
  policyButtonText: {
    color: '#3B82F6',
    fontSize: 16,
    fontWeight: '600',
  },
  euRightsButton: {
    backgroundColor: '#1A1A1A',
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    padding: 16,
    margin: 20,
    marginTop: 0,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: '#8B5CF6',
    gap: 8,
  },
  euRightsButtonText: {
    color: '#8B5CF6',
    fontSize: 16,
    fontWeight: '600',
  },
});

export default ConsentDashboard;
