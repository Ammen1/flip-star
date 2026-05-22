import React, { useState } from 'react';
import { View, Text, TouchableOpacity, Alert, ActivityIndicator, ScrollView, StyleSheet } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../api';

const DataExportScreen = ({ navigation }) => {
  const [loading, setLoading] = useState(false);
  const [exportStatus, setExportStatus] = useState('');
  const [exportData, setExportData] = useState(null);

  const handleDataExport = async () => {
    setLoading(true);
    setExportStatus('Preparing your data...');

    try {
      const response = await api.request('/auth/export-data/', {
        method: 'POST'
      });

      if (response.export_url) {
        setExportStatus('Data export ready!');
        setExportData(response.export_data);
        Alert.alert(
          'Data Export Ready',
          'Your personal data has been exported. You can view the summary below or download the complete file.',
          [
            { text: 'View Summary' },
            { text: 'OK' }
          ]
        );
      } else if (response.message) {
        setExportStatus('Processing...');
        Alert.alert(
          'Processing',
          response.message || 'Your data export is being processed. You will receive an email when it\'s ready.',
          [
            { text: 'OK' }
          ]
        );
      }
    } catch (error) {
      setExportStatus('');
      Alert.alert('Error', 'Failed to export data. Please try again later.');
    } finally {
      setLoading(false);
    }
  };

  const formatFileSize = (bytes) => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  return (
    <ScrollView style={styles.container}>
      <View style={styles.header}>
        <Ionicons name="download" size={48} color="#8fc441" />
        <Text style={styles.title}>Export Your Data</Text>
        <Text style={styles.subtitle}>Download a copy of your personal information</Text>
      </View>

      <View style={styles.section}>
        <Text style={styles.sectionTitle}>What's Included</Text>
        <View style={styles.dataList}>
          <View style={styles.dataItem}>
            <Ionicons name="person" size={20} color="#8fc441" />
            <Text style={styles.dataText}>Profile information</Text>
          </View>
          <View style={styles.dataItem}>
            <Ionicons name="settings" size={20} color="#8fc441" />
            <Text style={styles.dataText}>Account settings</Text>
          </View>
          <View style={styles.dataItem}>
            <Ionicons name="videocam" size={20} color="#8fc441" />
            <Text style={styles.dataText}>Content you've created</Text>
          </View>
          <View style={styles.dataItem}>
            <Ionicons name="chatbubble" size={20} color="#8fc441" />
            <Text style={styles.dataText}>Comments and likes</Text>
          </View>
          <View style={styles.dataItem}>
            <Ionicons name="wallet" size={20} color="#8fc441" />
            <Text style={styles.dataText}>Transaction history</Text>
          </View>
          <View style={styles.dataItem}>
            <Ionicons name="trophy" size={20} color="#8fc441" />
            <Text style={styles.dataText}>Campaign participation</Text>
          </View>
        </View>
      </View>

      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Export Format</Text>
        <View style={styles.formatCard}>
          <Ionicons name="document-text" size={24} color="#6B7280" />
          <View style={styles.formatInfo}>
            <Text style={styles.formatTitle}>JSON Format</Text>
            <Text style={styles.formatDescription}>
              Your data will be provided in JSON format, which can be opened in any text editor or imported into other applications.
            </Text>
          </View>
        </View>
      </View>

      {exportData && (
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Export Summary</Text>
          <View style={styles.summaryCard}>
            <Text style={styles.summaryItem}>
              Profile: {exportData.profile ? '✓' : '✗'}
            </Text>
            <Text style={styles.summaryItem}>
              Posts: {exportData.posts?.length || 0} items
            </Text>
            <Text style={styles.summaryItem}>
              Comments: {exportData.comments?.length || 0} items
            </Text>
            <Text style={styles.summaryItem}>
              Transactions: {exportData.transactions?.length || 0} items
            </Text>
            <Text style={styles.summaryItem}>
              Total Size: {exportData.data_size ? formatFileSize(exportData.data_size) : 'Unknown'}
            </Text>
          </View>
        </View>
      )}

        <TouchableOpacity 
          style={[styles.exportButton, loading && styles.exportButtonDisabled]}
          onPress={handleDataExport}
          disabled={loading}
        >
          {loading ? (
            <ActivityIndicator color="#fff" />
          ) : (
            <>
              <Ionicons name="download" size={20} color="#fff" />
              <Text style={styles.exportButtonText}>Export My Data</Text>
            </>
          )}
        </TouchableOpacity>

      {exportStatus ? (
        <Text style={styles.statusText}>{exportStatus}</Text>
      ) : null}

      <View style={styles.infoSection}>
        <Text style={styles.infoTitle}>Important Information</Text>
        <Text style={styles.infoText}>
          • Your data export will include all personal information associated with your account.
        </Text>
        <Text style={styles.infoText}>
          • The export process may take several minutes depending on the amount of data.
        </Text>
        <Text style={styles.infoText}>
          • You can request a new export at any time, but previous exports will be overwritten.
        </Text>
        <Text style={styles.infoText}>
          • For security reasons, export links expire after 7 days.
        </Text>
      </View>
    </ScrollView>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#0D0D0D',
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
  section: {
    margin: 20,
  },
  sectionTitle: {
    color: '#fff',
    fontSize: 20,
    fontWeight: '600',
    marginBottom: 16,
  },
  dataList: {
    backgroundColor: '#1A1A1A',
    borderRadius: 12,
    borderWidth: 1,
    borderColor: '#262626',
  },
  dataItem: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 16,
    borderBottomWidth: 1,
    borderBottomColor: '#262626',
  },
  dataText: {
    color: '#fff',
    fontSize: 16,
    marginLeft: 12,
  },
  formatCard: {
    backgroundColor: '#1A1A1A',
    borderRadius: 12,
    padding: 16,
    borderWidth: 1,
    borderColor: '#262626',
    flexDirection: 'row',
    alignItems: 'center',
  },
  formatInfo: {
    marginLeft: 16,
    flex: 1,
  },
  formatTitle: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
    marginBottom: 4,
  },
  formatDescription: {
    color: '#888',
    fontSize: 14,
    lineHeight: 20,
  },
  summaryCard: {
    backgroundColor: '#1A1A1A',
    borderRadius: 12,
    padding: 16,
    borderWidth: 1,
    borderColor: '#262626',
  },
  summaryItem: {
    color: '#ccc',
    fontSize: 14,
    marginBottom: 8,
  },
  exportButton: {
    backgroundColor: '#8fc441',
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    padding: 16,
    margin: 20,
    borderRadius: 12,
    gap: 8,
  },
  exportButtonDisabled: {
    backgroundColor: '#333',
  },
  exportButtonText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
  },
  statusText: {
    color: '#10B981',
    fontSize: 14,
    textAlign: 'center',
    margin: 20,
  },
  infoSection: {
    backgroundColor: '#1A1A1A',
    margin: 20,
    padding: 16,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: '#262626',
  },
  infoTitle: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
    marginBottom: 12,
  },
  infoText: {
    color: '#888',
    fontSize: 14,
    lineHeight: 20,
    marginBottom: 8,
  },
});

export default DataExportScreen;
