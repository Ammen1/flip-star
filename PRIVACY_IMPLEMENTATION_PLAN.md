# FlipStar Privacy Features Implementation Plan

## Executive Summary

This document outlines all privacy features that need to be implemented in the FlipStar app to achieve full Google Play privacy policy compliance. Each feature includes detailed implementation requirements, code examples, and integration points.

## 1. Prominent Disclosure System

### **Current Status: ❌ NOT IMPLEMENTED**

### **Required Implementation:**

**1.1 Camera Access Disclosure**
```javascript
// File: src/components/CameraDisclosure.js
import React, { useState } from 'react';
import { View, Text, Alert, TouchableOpacity } from 'react-native';

const CameraDisclosure = ({ onAccept, onDecline }) => {
  return (
    <View style={styles.disclosureContainer}>
      <Text style={styles.title}>Camera Access Required</Text>
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
      <View style={styles.buttonContainer}>
        <TouchableOpacity style={styles.declineButton} onPress={onDecline}>
          <Text style={styles.declineText}>Decline</Text>
        </TouchableOpacity>
        <TouchableOpacity style={styles.acceptButton} onPress={onAccept}>
          <Text style={styles.acceptText}>Allow Camera Access</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
};

export default CameraDisclosure;
```

**1.2 Storage Access Disclosure**
```javascript
// File: src/components/StorageDisclosure.js
const StorageDisclosure = ({ onAccept, onDecline }) => {
  return (
    <View style={styles.disclosureContainer}>
      <Text style={styles.title}>Storage Access Required</Text>
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
      <View style={styles.buttonContainer}>
        <TouchableOpacity style={styles.declineButton} onPress={onDecline}>
          <Text style={styles.declineText}>Decline</Text>
        </TouchableOpacity>
        <TouchableOpacity style={styles.acceptButton} onPress={onAccept}>
          <Text style={styles.acceptText}>Allow Storage Access</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
};
```

**1.3 Integration with CreateScreen**
```javascript
// File: src/screens/CreateScreen.js (Modified)
import CameraDisclosure from '../components/CameraDisclosure';
import StorageDisclosure from '../components/StorageDisclosure';

const CreateScreen = () => {
  const [showCameraDisclosure, setShowCameraDisclosure] = useState(false);
  const [showStorageDisclosure, setShowStorageDisclosure] = useState(false);
  const [consents, setConsents] = useState({
    camera: false,
    storage: false
  });

  const pickFromLibrary = async () => {
    if (!consents.storage) {
      setShowStorageDisclosure(true);
      return;
    }
    // Existing implementation
  };

  const pickPhotoFromCamera = async () => {
    if (!consents.camera) {
      setShowCameraDisclosure(true);
      return;
    }
    // Existing implementation
  };

  return (
    <View style={styles.container}>
      {/* Existing UI */}
      
      {/* Camera Disclosure Modal */}
      <Modal visible={showCameraDisclosure} transparent>
        <CameraDisclosure
          onAccept={() => {
            setConsents(prev => ({ ...prev, camera: true }));
            setShowCameraDisclosure(false);
            // Proceed with camera access
          }}
          onDecline={() => {
            setShowCameraDisclosure(false);
            Alert.alert('Permission Denied', 'Camera access is required to create content.');
          }}
        />
      </Modal>

      {/* Storage Disclosure Modal */}
      <Modal visible={showStorageDisclosure} transparent>
        <StorageDisclosure
          onAccept={() => {
            setConsents(prev => ({ ...prev, storage: true }));
            setShowStorageDisclosure(false);
            // Proceed with storage access
          }}
          onDecline={() => {
            setShowStorageDisclosure(false);
            Alert.alert('Permission Denied', 'Storage access is required to save content.');
          }}
        />
      </Modal>
    </View>
  );
};
```

## 2. Account Deletion System

### **Current Status: ❌ NOT IMPLEMENTED**

### **Required Implementation:**

**2.1 Account Deletion Screen**
```javascript
// File: src/screens/AccountDeletionScreen.js
import React, { useState } from 'react';
import { View, Text, TouchableOpacity, Alert, ScrollView } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../api';

const AccountDeletionScreen = ({ navigation }) => {
  const [loading, setLoading] = useState(false);
  const [confirmed, setConfirmed] = useState(false);

  const handleDeleteAccount = async () => {
    if (!confirmed) {
      Alert.alert('Confirmation Required', 'Please check the confirmation box below to proceed.');
      return;
    }

    Alert.alert(
      'Delete Account',
      'This will permanently delete your account and all associated data including:\n\n• Profile information\n• Uploaded content\n• Comments and likes\n• Transaction history\n• Campaign participation data\n\nThis action cannot be undone. Are you sure?',
      [
        { text: 'Cancel', style: 'cancel' },
        { 
          text: 'Delete', 
          style: 'destructive',
          onPress: performDeletion
        }
      ]
    );
  };

  const performDeletion = async () => {
    setLoading(true);
    try {
      await api.request('/auth/delete-account/', { method: 'DELETE' });
      
      // Clear local storage
      await SecureStore.deleteItemAsync('auth_token');
      await AsyncStorage.removeItem('userPreferences');
      
      Alert.alert(
        'Account Deleted',
        'Your account has been successfully deleted. We hope to see you again soon!',
        [
          { 
            text: 'OK', 
            onPress: () => {
              navigation.reset({
                index: 0,
                routes: [{ name: 'Login' }]
              });
            }
          }
        ]
      );
    } catch (error) {
      Alert.alert('Error', 'Failed to delete account. Please contact support for assistance.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <ScrollView style={styles.container}>
      <View style={styles.header}>
        <Ionicons name="warning" size={48} color="#FF4444" />
        <Text style={styles.title}>Delete Account</Text>
      </View>

      <View style={styles.warningSection}>
        <Text style={styles.warningTitle}>⚠️ Important Information</Text>
        <Text style={styles.warningText}>
          Account deletion is permanent and cannot be undone. Once your account is deleted:
        </Text>
        <View style={styles.consequencesList}>
          <Text style={styles.consequenceItem}>• All your content will be permanently removed</Text>
          <Text style={styles.consequenceItem}>• Your username will become available to others</Text>
          <Text style={styles.consequenceItem}>• All transaction history will be deleted</Text>
          <Text style={styles.consequenceItem}>• Campaign participation records will be removed</Text>
          <Text style={styles.consequenceItem}>• You will lose access to any purchased coins</Text>
        </View>
      </View>

      <View style={styles.dataRetentionSection}>
        <Text style={styles.sectionTitle}>Data Retention</Text>
        <Text style={styles.sectionText}>
          Some data may be retained for legal or security purposes:
        </Text>
        <View style={styles.retentionList}>
          <Text style={styles.retentionItem}>• Transaction records for 7 years (legal requirement)</Text>
          <Text style={styles.retentionItem}>• Security logs for 90 days</Text>
          <Text style={styles.retentionItem}>• Deleted content backups for 30 days</Text>
        </View>
      </View>

      <View style={styles.confirmationSection}>
        <TouchableOpacity 
          style={styles.checkboxContainer}
          onPress={() => setConfirmed(!confirmed)}
        >
          <View style={[styles.checkbox, confirmed && styles.checkboxChecked]}>
            {confirmed && <Ionicons name="checkmark" size={16} color="#fff" />}
          </View>
          <Text style={styles.checkboxText}>
            I understand that account deletion is permanent and cannot be undone
          </Text>
        </TouchableOpacity>
      </View>

      <TouchableOpacity 
        style={[styles.deleteButton, (!confirmed || loading) && styles.deleteButtonDisabled]}
        onPress={handleDeleteAccount}
        disabled={!confirmed || loading}
      >
        {loading ? (
          <ActivityIndicator color="#fff" />
        ) : (
          <Text style={styles.deleteButtonText}>Delete My Account</Text>
        )}
      </TouchableOpacity>

      <TouchableOpacity 
        style={styles.cancelButton}
        onPress={() => navigation.goBack()}
      >
        <Text style={styles.cancelButtonText}>Keep My Account</Text>
      </TouchableOpacity>
    </ScrollView>
  );
};

export default AccountDeletionScreen;
```

**2.2 Backend API Endpoint**
```python
# File: backend/api/views.py
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from django.contrib.auth import get_user_model
from django.db import transaction
from django.core.files.storage import default_storage
import os

User = get_user_model()

@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_account(request):
    """
    Permanently delete user account and all associated data
    """
    try:
        with transaction.atomic():
            user = request.user
            
            # Delete user's content files
            if user.profile_photo:
                if default_storage.exists(user.profile_photo.name):
                    default_storage.delete(user.profile_photo.name)
            
            # Delete user's posts and associated media
            for post in user.posts.all():
                if post.media and default_storage.exists(post.media.name):
                    default_storage.delete(post.media.name)
                post.delete()
            
            # Delete user's campaign entries
            user.campaign_entries.all().delete()
            
            # Delete user's transactions (keep records for legal compliance)
            # Mark as deleted but retain for 7 years
            user.wallet_transactions.update(is_deleted=True, deleted_at=timezone.now())
            
            # Delete user's comments and likes
            user.comments.all().delete()
            user.likes.all().delete()
            
            # Delete user's notifications
            user.notifications.all().delete()
            
            # Delete user's reports
            user.reports_made.all().delete()
            user.reports_received.all().delete()
            
            # Delete user's blocked relationships
            user.blocked_users.all().delete()
            user.blocked_by.all().delete()
            
            # Finally delete the user account
            user.delete()
            
        return Response({'message': 'Account successfully deleted'}, status=200)
        
    except Exception as e:
        return Response({'error': str(e)}, status=500)
```

**2.3 Web-Based Account Deletion**
```html
<!-- File: frontend/account-deletion.html -->
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Delete FlipStar Account</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
</head>
<body>
    <div class="container mt-5">
        <div class="row justify-content-center">
            <div class="col-md-8">
                <div class="card">
                    <div class="card-header bg-danger text-white">
                        <h3>Delete Your FlipStar Account</h3>
                    </div>
                    <div class="card-body">
                        <form id="deleteForm">
                            <div class="alert alert-warning">
                                <h5>⚠️ Important Notice</h5>
                                <p>Account deletion is permanent and cannot be undone. All your data will be permanently removed.</p>
                            </div>
                            
                            <div class="mb-3">
                                <label for="email" class="form-label">Email Address</label>
                                <input type="email" class="form-control" id="email" required>
                                <div class="form-text">Enter your registered email address</div>
                            </div>
                            
                            <div class="mb-3">
                                <label for="reason" class="form-label">Reason for Leaving (Optional)</label>
                                <select class="form-select" id="reason">
                                    <option value="">Select a reason</option>
                                    <option value="privacy">Privacy concerns</option>
                                    <option value="usage">Don't use the app anymore</option>
                                    <option value="technical">Technical issues</option>
                                    <option value="content">Content concerns</option>
                                    <option value="other">Other</option>
                                </select>
                            </div>
                            
                            <div class="mb-3">
                                <label for="feedback" class="form-label">Feedback (Optional)</label>
                                <textarea class="form-control" id="feedback" rows="3"></textarea>
                            </div>
                            
                            <div class="mb-3 form-check">
                                <input type="checkbox" class="form-check-input" id="confirmation" required>
                                <label class="form-check-label" for="confirmation">
                                    I understand that account deletion is permanent and cannot be undone
                                </label>
                            </div>
                            
                            <button type="submit" class="btn btn-danger">Delete My Account</button>
                            <a href="/" class="btn btn-secondary">Cancel</a>
                        </form>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        document.getElementById('deleteForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            
            const email = document.getElementById('email').value;
            const confirmation = document.getElementById('confirmation').checked;
            
            if (!confirmation) {
                alert('Please confirm that you understand account deletion is permanent.');
                return;
            }
            
            try {
                const response = await fetch('/api/delete-account/', {
                    method: 'DELETE',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ email })
                });
                
                if (response.ok) {
                    alert('Account deletion request submitted successfully.');
                    window.location.href = '/';
                } else {
                    const error = await response.json();
                    alert('Error: ' + error.message);
                }
            } catch (error) {
                alert('An error occurred. Please try again.');
            }
        });
    </script>
</body>
</html>
```

## 3. Consent Management System

### **Current Status: ❌ NOT IMPLEMENTED**

### **Required Implementation:**

**3.1 Consent Management Context**
```javascript
// File: src/contexts/ConsentContext.js
import React, { createContext, useContext, useState, useEffect } from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';

const ConsentContext = createContext();

export const useConsent = () => {
  const context = useContext(ConsentContext);
  if (!context) {
    throw new Error('useConsent must be used within ConsentProvider');
  }
  return context;
};

export const ConsentProvider = ({ children }) => {
  const [consents, setConsents] = useState({
    camera: false,
    storage: false,
    analytics: false,
    marketing: false,
    functional: true, // Essential for app functionality
    necessary: true   // Required for basic operation
  });

  const [consentHistory, setConsentHistory] = useState([]);

  useEffect(() => {
    loadConsents();
  }, []);

  const loadConsents = async () => {
    try {
      const stored = await AsyncStorage.getItem('userConsents');
      if (stored) {
        setConsents(JSON.parse(stored));
      }
      
      const history = await AsyncStorage.getItem('consentHistory');
      if (history) {
        setConsentHistory(JSON.parse(history));
      }
    } catch (error) {
      console.log('Error loading consents:', error);
    }
  };

  const updateConsent = async (type, granted) => {
    const newConsents = { ...consents, [type]: granted };
    setConsents(newConsents);
    
    try {
      await AsyncStorage.setItem('userConsents', JSON.stringify(newConsents));
      
      // Record consent change
      const historyEntry = {
        type,
        granted,
        timestamp: new Date().toISOString(),
        appVersion: '1.0.0'
      };
      
      const newHistory = [...consentHistory, historyEntry];
      setConsentHistory(newHistory);
      await AsyncStorage.setItem('consentHistory', JSON.stringify(newHistory));
      
    } catch (error) {
      console.log('Error saving consent:', error);
    }
  };

  const withdrawConsent = (type) => {
    updateConsent(type, false);
    
    // Handle consent withdrawal
    switch (type) {
      case 'camera':
        // Disable camera-related features
        break;
      case 'storage':
        // Clear local storage
        break;
      case 'analytics':
        // Stop analytics tracking
        break;
      case 'marketing':
        // Unsubscribe from marketing
        break;
    }
  };

  const hasConsent = (type) => {
    return consents[type] || false;
  };

  return (
    <ConsentContext.Provider value={{
      consents,
      consentHistory,
      updateConsent,
      withdrawConsent,
      hasConsent
    }}>
      {children}
    </ConsentContext.Provider>
  );
};
```

**3.2 Consent Dashboard Screen**
```javascript
// File: src/screens/ConsentDashboard.js
import React from 'react';
import { View, Text, TouchableOpacity, ScrollView } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useConsent } from '../contexts/ConsentContext';

const ConsentDashboard = ({ navigation }) => {
  const { consents, updateConsent, withdrawConsent, consentHistory } = useConsent();

  const consentItems = [
    {
      key: 'camera',
      title: 'Camera Access',
      description: 'Allow app to access camera for creating content',
      icon: 'camera',
      required: false
    },
    {
      key: 'storage',
      title: 'Storage Access',
      description: 'Allow app to access device storage for saving content',
      icon: 'folder',
      required: false
    },
    {
      key: 'analytics',
      title: 'Analytics Data',
      description: 'Help us improve the app by sharing usage analytics',
      icon: 'analytics',
      required: false
    },
    {
      key: 'marketing',
      title: 'Marketing Communications',
      description: 'Receive updates about new features and promotions',
      icon: 'mail',
      required: false
    },
    {
      key: 'functional',
      title: 'Functional Data',
      description: 'Essential data for app functionality (cannot be disabled)',
      icon: 'settings',
      required: true
    },
    {
      key: 'necessary',
      title: 'Necessary Data',
      description: 'Required for basic app operation (cannot be disabled)',
      icon: 'lock-closed',
      required: true
    }
  ];

  return (
    <ScrollView style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.title}>Privacy Settings</Text>
        <Text style={styles.subtitle}>Manage your data sharing preferences</Text>
      </View>

      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Data Permissions</Text>
        {consentItems.map(item => (
          <View key={item.key} style={styles.consentItem}>
            <View style={styles.consentInfo}>
              <Ionicons name={item.icon} size={24} color="#666" />
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
          consentHistory.slice(-5).map((entry, index) => (
            <View key={index} style={styles.historyItem}>
              <Text style={styles.historyText}>
                {entry.type} - {entry.granted ? 'Granted' : 'Withdrawn'}
              </Text>
              <Text style={styles.historyDate}>
                {new Date(entry.timestamp).toLocaleDateString()}
              </Text>
            </View>
          ))
        )}
      </View>

      <TouchableOpacity style={styles.exportButton}>
        <Text style={styles.exportButtonText}>Export My Data</Text>
      </TouchableOpacity>
    </ScrollView>
  );
};

export default ConsentDashboard;
```

## 4. Data Export System

### **Current Status: ❌ NOT IMPLEMENTED**

### **Required Implementation:**

**4.1 Data Export Screen**
```javascript
// File: src/screens/DataExportScreen.js
import React, { useState } from 'react';
import { View, Text, TouchableOpacity, Alert, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../api';

const DataExportScreen = () => {
  const [loading, setLoading] = useState(false);
  const [exportStatus, setExportStatus] = useState('');

  const handleDataExport = async () => {
    setLoading(true);
    setExportStatus('Preparing your data...');

    try {
      const response = await api.request('/auth/export-data/', {
        method: 'POST'
      });

      if (response.export_url) {
        setExportStatus('Data export ready!');
        Alert.alert(
          'Data Export Ready',
          'Your personal data has been exported and is ready for download. You will receive an email with a secure download link.',
          [
            { text: 'OK' }
          ]
        );
      } else {
        setExportStatus('Processing...');
        Alert.alert(
          'Processing',
          'Your data export is being processed. You will receive an email when it\'s ready.',
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

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Ionicons name="download" size={48} color="#3B82F6" />
        <Text style={styles.title}>Export Your Data</Text>
        <Text style={styles.subtitle}>Download a copy of your personal information</Text>
      </View>

      <View style={styles.section}>
        <Text style={styles.sectionTitle}>What's Included</Text>
        <View style={styles.dataList}>
          <Text style={styles.dataItem}>• Profile information</Text>
          <Text style={styles.dataItem}>• Account settings</Text>
          <Text style={styles.dataItem}>• Content you've created</Text>
          <Text style={styles.dataItem}>• Comments and likes</Text>
          <Text style={styles.dataItem}>• Transaction history</Text>
          <Text style={styles.dataItem}>• Campaign participation</Text>
        </View>
      </View>

      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Export Format</Text>
        <Text style={styles.description}>
          Your data will be provided in JSON format, which can be opened in any text editor or imported into other applications.
        </Text>
      </View>

      <TouchableOpacity 
        style={styles.exportButton}
        onPress={handleDataExport}
        disabled={loading}
      >
        {loading ? (
          <ActivityIndicator color="#fff" />
        ) : (
          <Text style={styles.exportButtonText}>Export My Data</Text>
        )}
      </TouchableOpacity>

      {exportStatus ? (
        <Text style={styles.statusText}>{exportStatus}</Text>
      ) : null}
    </View>
  );
};

export default DataExportScreen;
```

**4.2 Backend Data Export API**
```python
# File: backend/api/views.py
import json
from datetime import datetime
from django.http import JsonResponse
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
import zipfile
import io

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def export_user_data(request):
    """
    Export all user data in JSON format
    """
    try:
        user = request.user
        
        # Collect all user data
        export_data = {
            'export_info': {
                'date': datetime.now().isoformat(),
                'user_id': user.id,
                'username': user.username,
                'email': user.email
            },
            'profile': {
                'username': user.username,
                'email': user.email,
                'full_name': user.full_name,
                'phone_number': user.phone_number,
                'profile_photo': user.profile_photo.url if user.profile_photo else None,
                'bio': user.bio,
                'created_at': user.created_at.isoformat(),
                'last_login': user.last_login.isoformat() if user.last_login else None
            },
            'posts': [
                {
                    'id': post.id,
                    'caption': post.caption,
                    'hashtags': post.hashtags,
                    'media': post.media.url if post.media else None,
                    'created_at': post.created_at.isoformat(),
                    'is_campaign_post': post.is_campaign_post,
                    'campaign_id': post.campaign_id
                }
                for post in user.posts.all()
            ],
            'comments': [
                {
                    'id': comment.id,
                    'content': comment.content,
                    'post_id': comment.post_id,
                    'created_at': comment.created_at.isoformat()
                }
                for comment in user.comments.all()
            ],
            'likes': [
                {
                    'id': like.id,
                    'post_id': like.post_id,
                    'created_at': like.created_at.isoformat()
                }
                for like in user.likes.all()
            ],
            'campaign_entries': [
                {
                    'id': entry.id,
                    'campaign_id': entry.campaign_id,
                    'reel_id': entry.reel_id,
                    'created_at': entry.created_at.isoformat()
                }
                for entry in user.campaign_entries.all()
            ],
            'transactions': [
                {
                    'id': transaction.id,
                    'amount': transaction.amount,
                    'transaction_type': transaction.transaction_type,
                    'description': transaction.description,
                    'created_at': transaction.created_at.isoformat()
                }
                for transaction in user.wallet_transactions.filter(is_deleted=False)
            ],
            'notifications': [
                {
                    'id': notification.id,
                    'type': notification.type,
                    'content': notification.content,
                    'created_at': notification.created_at.isoformat()
                }
                for notification in user.notifications.all()
            ]
        }

        # Create JSON file
        json_data = json.dumps(export_data, indent=2, default=str)
        
        # Create ZIP file
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            zip_file.writestr('flipstar_data_export.json', json_data)
        
        zip_buffer.seek(0)
        
        # Here you would typically upload to cloud storage and send download link
        # For now, return the data directly
        return JsonResponse({
            'message': 'Data export prepared successfully',
            'data_size': len(json_data),
            'export_data': export_data
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
```

## 5. Enhanced Privacy Policy

### **Current Status: ❌ NOT IMPLEMENTED**

### **Required Implementation:**

**5.1 Privacy Policy Screen**
```javascript
// File: src/screens/PrivacyPolicyScreen.js
import React from 'react';
import { View, Text, ScrollView, Linking } from 'react-native';

const PrivacyPolicyScreen = () => {
  const privacyPolicyContent = `
# FlipStar Privacy Policy

**Last Updated:** May 22, 2026  
**Effective Date:** May 22, 2026

## 1. Developer Information

**Company:** SkykinTechnologies PLC  
**Contact:** privacy@flipstar.et  
**Website:** https://flipstar.et  
**Address:** [Company Address]

## 2. Information We Collect

### Personal Information
- Full name, username, email address
- Phone number for verification and payments
- Profile photos and bio information
- Date of birth (for age verification)

### Content Data
- Videos and photos you upload
- Captions, comments, and hashtags
- Campaign participation data
- Social interactions (likes, shares, follows)

### Financial Information
- Payment method information (processed securely by telebirr)
- Transaction history and coin purchases
- Subscription billing information

### Usage Data
- App interactions and preferences
- Device information for compatibility
- Performance and crash data

## 3. How We Use Your Information

### Core App Functionality
- Provide and maintain our service
- Process payments and manage subscriptions
- Enable content creation and sharing
- Facilitate social interactions

### Personalization
- Customize your app experience
- Recommend relevant content
- Display appropriate campaigns

### Safety and Security
- Verify user identity
- Detect and prevent fraud
- Enforce community guidelines

### Legal Compliance
- Comply with applicable laws
- Respond to legal requests
- Protect our rights and property

## 4. Information Sharing

We do not sell your personal information. We only share data in limited circumstances:

### Service Providers
- Payment processors (telebirr)
- Cloud storage providers
- Analytics services (with consent)

### Legal Requirements
- When required by law
- To protect our rights
- In case of merger or acquisition

## 5. Data Security

We implement appropriate security measures including:
- HTTPS encryption for all data transmission
- Secure authentication systems
- Regular security audits
- Access controls and monitoring

## 6. Data Retention

We retain your data as follows:
- Account data: Until account deletion
- Content: Until you delete it or account deletion
- Transaction records: 7 years (legal requirement)
- Security logs: 90 days

## 7. Your Rights

You have the right to:
- Access your personal data
- Correct inaccurate information
- Delete your account and data
- Export your data
- Object to processing
- Withdraw consent

## 8. Children's Privacy

Our service is not intended for children under 18. We do not knowingly collect information from children under 18.

## 9. International Data Transfers

We transfer data internationally using:
- EU-U.S. Data Privacy Framework
- Standard Contractual Clauses
- Adequate level of protection

## 10. Changes to This Policy

We may update this privacy policy from time to time. We will notify you of any changes by:
- Posting the new policy in the app
- Sending email notifications
- In-app notifications

## 11. Contact Us

If you have questions about this privacy policy, please contact us:
- Email: privacy@flipstar.et
- Address: [Company Address]
- Phone: [Company Phone]

## 12. Account Deletion

You can delete your account at any time through:
- The app settings menu
- Our website at flipstar.et/delete-account
- Contacting our support team

When you delete your account, we will permanently delete your personal information within 30 days, except where we are required by law to retain certain data.
  `;

  return (
    <ScrollView style={styles.container}>
      <Text style={styles.content}>{privacyPolicyContent}</Text>
    </ScrollView>
  );
};

export default PrivacyPolicyScreen;
```

## 6. EU Data Compliance Features

### **Current Status: ❌ NOT IMPLEMENTED**

### **Required Implementation:**

**6.1 GDPR Consent Banner**
```javascript
// File: src/components/GDPRConsentBanner.js
import React, { useState } from 'react';
import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';

const GDPRConsentBanner = ({ onAccept, onCustomize }) => {
  return (
    <View style={styles.banner}>
      <Text style={styles.bannerText}>
        We use cookies and similar technologies to help personalize content, tailor and measure ads, and provide a better experience.
      </Text>
      <View style={styles.buttonContainer}>
        <TouchableOpacity style={styles.customizeButton} onPress={onCustomize}>
          <Text style={styles.customizeButtonText}>Customize</Text>
        </TouchableOpacity>
        <TouchableOpacity style={styles.acceptButton} onPress={onAccept}>
          <Text style={styles.acceptButtonText}>Accept All</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
};

export default GDPRConsentBanner;
```

**6.2 EU User Rights Screen**
```javascript
// File: src/screens/EURightsScreen.js
import React from 'react';
import { View, Text, ScrollView, TouchableOpacity } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

const EURightsScreen = ({ navigation }) => {
  const rights = [
    {
      title: 'Right to Information',
      description: 'Know what data we collect and why',
      icon: 'information-circle'
    },
    {
      title: 'Right to Access',
      description: 'Get a copy of your personal data',
      icon: 'download'
    },
    {
      title: 'Right to Rectification',
      description: 'Correct inaccurate personal data',
      icon: 'create'
    },
    {
      title: 'Right to Erasure',
      description: 'Delete your personal data',
      icon: 'trash'
    },
    {
      title: 'Right to Restrict Processing',
      description: 'Limit how we use your data',
      icon: 'lock-closed'
    },
    {
      title: 'Right to Data Portability',
      description: 'Transfer your data to another service',
      icon: 'swap-horizontal'
    },
    {
      title: 'Right to Object',
      description: 'Object to certain data processing',
      icon: 'close-circle'
    },
    {
      title: 'Rights Related to Automated Decision Making',
      description: 'Human review of automated decisions',
      icon: 'people'
    }
  ];

  return (
    <ScrollView style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.title}>Your GDPR Rights</Text>
        <Text style={styles.subtitle}>Your privacy rights under EU law</Text>
      </View>

      {rights.map((right, index) => (
        <TouchableOpacity key={index} style={styles.rightItem}>
          <View style={styles.rightIcon}>
            <Ionicons name={right.icon} size={24} color="#3B82F6" />
          </View>
          <View style={styles.rightContent}>
            <Text style={styles.rightTitle}>{right.title}</Text>
            <Text style={styles.rightDescription}>{right.description}</Text>
          </View>
          <Ionicons name="chevron-forward" size={20} color="#666" />
        </TouchableOpacity>
      ))}
    </ScrollView>
  );
};

export default EURightsScreen;
```

## 7. Integration Requirements

### **7.1 App Navigation Updates**
```javascript
// File: src/navigation/AppNavigator.js (Modified)
import ConsentDashboard from '../screens/ConsentDashboard';
import AccountDeletionScreen from '../screens/AccountDeletionScreen';
import DataExportScreen from '../screens/DataExportScreen';
import EURightsScreen from '../screens/EURightsScreen';

// Add new screens to navigation stack
const MainTabNavigator = () => {
  return (
    <Tab.Navigator>
      {/* Existing tabs */}
      
      <Tab.Screen 
        name="Privacy" 
        component={PrivacySettingsScreen}
        options={{
          tabBarLabel: 'Privacy',
          tabBarIcon: ({ color, size }) => (
            <Ionicons name="lock-closed" size={size} color={color} />
          )
        }}
      />
    </Tab.Navigator>
  );
};
```

### **7.2 Settings Screen Updates**
```javascript
// File: src/screens/SettingsScreen.js (Modified)
const SettingRow = ({ icon, label, onPress, colors }) => (
  <TouchableOpacity style={[styles.settingRow, { backgroundColor: colors.cardBg }]} onPress={onPress}>
    <Ionicons name={icon} size={24} color={colors.primary} />
    <Text style={[styles.settingText, { color: colors.text }]}>{label}</Text>
    <Ionicons name="chevron-forward" size={20} color={colors.textSecondary} />
  </TouchableOpacity>
);

// Add new privacy settings
<SettingRow 
  icon="shield-checkmark" 
  label="Privacy Dashboard" 
  onPress={() => navigation.navigate('ConsentDashboard')} 
  colors={colors} 
/>
<SettingRow 
  icon="download" 
  label="Export My Data" 
  onPress={() => navigation.navigate('DataExport')} 
  colors={colors} 
/>
<SettingRow 
  icon="trash" 
  label="Delete Account" 
  onPress={() => navigation.navigate('AccountDeletion')} 
  colors={colors} 
/>
<SettingRow 
  icon="balance" 
  label="EU Privacy Rights" 
  onPress={() => navigation.navigate('EURights')} 
  colors={colors} 
/>
```

## 8. Implementation Timeline

### **Phase 1: Critical Compliance (2-4 weeks)**
1. **Prominent Disclosure System**
   - Camera disclosure component
   - Storage disclosure component
   - Integration with CreateScreen
   - Consent tracking system

2. **Account Deletion Feature**
   - Account deletion screen
   - Backend API endpoint
   - Web-based deletion form
   - Data retention policies

### **Phase 2: Enhanced Privacy (4-8 weeks)**
1. **Consent Management System**
   - Consent context provider
   - Consent dashboard screen
   - Consent history tracking
   - Withdrawal mechanisms

2. **Data Export System**
   - Data export screen
   - Backend export API
   - Export format standardization
   - Secure delivery mechanisms

### **Phase 3: Full Compliance (8-12 weeks)**
1. **Enhanced Privacy Policy**
   - Comprehensive privacy policy screen
   - Web privacy policy page
   - Policy update notifications
   - Legal review integration

2. **EU Data Compliance**
   - GDPR consent banner
   - EU rights implementation
   - Data transfer mechanisms
   - Compliance reporting

## 9. Testing Requirements

### **9.1 Privacy Feature Testing**
```javascript
// File: __tests__/privacy/ConsentSystem.test.js
import { render, fireEvent } from '@testing-library/react-native';
import { ConsentProvider, useConsent } from '../../contexts/ConsentContext';

describe('Consent System', () => {
  test('should update consent correctly', async () => {
    const TestComponent = () => {
      const { consents, updateConsent } = useConsent();
      
      return (
        <TouchableOpacity 
          testID="camera-consent" 
          onPress={() => updateConsent('camera', true)}
        >
          <Text>Camera: {consents.camera ? 'Granted' : 'Denied'}</Text>
        </TouchableOpacity>
      );
    };

    // Test implementation
  });
});
```

### **9.2 Account Deletion Testing**
```javascript
// File: __tests__/privacy/AccountDeletion.test.js
describe('Account Deletion', () => {
  test('should delete account successfully', async () => {
    // Mock API call
    // Test UI flow
    // Verify data deletion
  });
});
```

## 10. Success Metrics

### **10.1 Compliance Metrics**
- 100% prominent disclosure implementation
- 100% account deletion functionality
- 100% consent management coverage
- 100% data export capability

### **10.2 User Experience Metrics**
- Consent completion rate > 90%
- Account deletion completion rate > 95%
- Data export success rate > 98%
- User satisfaction with privacy controls > 85%

### **10.3 Technical Metrics**
- Zero privacy policy violations
- 100% data encryption coverage
- Complete audit trail implementation
- Full GDPR compliance verification

---

**Implementation Priority:** Critical  
**Timeline:** 8-12 weeks  
**Compliance Target:** Google Play Policy, GDPR, CCPA  
**Next Review:** Weekly progress updates
