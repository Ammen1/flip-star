import React, { useState } from 'react';
import { View, Text, ScrollView, TouchableOpacity, StyleSheet, Alert, Modal, Linking } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useConsent } from '../contexts/ConsentContext';
import api from '../api';

const EURightsScreen = ({ navigation }) => {
  const { hasConsent, updateConsent } = useConsent();
  const [showDetailModal, setShowDetailModal] = useState(false);
  const [selectedRight, setSelectedRight] = useState(null);
  const [requestStatus, setRequestStatus] = useState('');
  const [loading, setLoading] = useState(false);

  const rights = [
    {
      title: 'Right to Information',
      description: 'Know what data we collect and why we collect it',
      icon: 'information-circle',
      color: '#8fc441',
      details: 'You have the right to know what personal data we collect about you, why we collect it, how we use it, and who we share it with. This includes information about data retention periods and your rights to complain to a supervisory authority.',
      legalBasis: 'Our legal basis for processing includes consent, contractual necessity, and legitimate interests.',
      dataTypes: 'Personal information, content, usage analytics, transaction data'
    },
    {
      title: 'Right to Access',
      description: 'Get a copy of your personal data',
      icon: 'download',
      color: '#8fc441',
      details: 'You can request a copy of all personal data we hold about you in a readable format. We provide this free of charge and will respond within 30 days.',
      action: 'export',
      procedure: 'Use the Data Export feature to download your complete data package instantly.'
    },
    {
      title: 'Right to Rectification',
      description: 'Correct inaccurate personal data',
      icon: 'create',
      color: '#8fc441',
      details: 'If your personal data is inaccurate or incomplete, you can ask us to correct it. We will correct errors promptly and notify you of the changes.',
      action: 'profile',
      procedure: 'Go to Edit Profile to update your personal information directly.'
    },
    {
      title: 'Right to Erasure',
      description: 'Delete your personal data',
      icon: 'trash',
      color: '#8fc441',
      details: 'You can ask us to delete your personal data in certain circumstances, such as when it\'s no longer needed for the purpose it was collected for, or if you withdraw consent.',
      action: 'delete',
      procedure: 'Contact our privacy team or use the account deletion process in settings.',
      exceptions: 'We may retain data for legal compliance, fraud prevention, and legitimate interests.'
    },
    {
      title: 'Right to Restrict Processing',
      description: 'Limit how we use your data',
      icon: 'lock-closed',
      color: '#8fc441',
      details: 'You can ask us to restrict the processing of your personal data in certain circumstances. When restricted, we can still store your data but not process it further.',
      action: 'restrict',
      procedure: 'Contact privacy@flipstar.et to request processing restrictions.'
    },
    {
      title: 'Right to Data Portability',
      description: 'Transfer your data to another service',
      icon: 'swap-horizontal',
      color: '#8fc441',
      details: 'You can ask us to transfer your personal data to another service provider in a machine-readable format. This applies to data you provided consent for.',
      action: 'export',
      procedure: 'Use Data Export to get your data in a portable JSON format.'
    },
    {
      title: 'Right to Object',
      description: 'Object to certain data processing',
      icon: 'close-circle',
      color: '#8fc441',
      details: 'You can object to certain types of processing, particularly direct marketing. We will stop processing unless we have compelling legitimate grounds.',
      action: 'object',
      procedure: 'Use Privacy Dashboard to withdraw marketing consent or contact privacy team.'
    },
    {
      title: 'Rights Related to Automated Decision Making',
      description: 'Human review of automated decisions',
      icon: 'people',
      color: '#8fc441',
      details: 'You have the right not to be subject to a decision based solely on automated processing, including profiling, that produces legal or similarly significant effects on you.',
      action: 'human-review',
      procedure: 'Request human review by contacting our DPO at privacy@flipstar.et.'
    }
  ];

  const handleRightAction = async (action) => {
    switch (action) {
      case 'export':
        navigation.navigate('DataExport');
        break;
      case 'profile':
        navigation.navigate('EditProfile');
        break;
      case 'delete':
        Alert.alert(
          'Account Deletion',
          'To delete your account and all associated data, please go to Settings > Account Management > Delete Account. This action cannot be undone.',
          [
            { text: 'Cancel', style: 'cancel' },
            { 
              text: 'Go to Settings', 
              onPress: () => navigation.navigate('Settings')
            }
          ]
        );
        break;
      case 'restrict':
        await handleProcessingRestriction();
        break;
      case 'object':
        await handleObjection();
        break;
      case 'human-review':
        await handleHumanReview();
        break;
      default:
        break;
    }
  };

  const handleRightPress = (right) => {
    setSelectedRight(right);
    setShowDetailModal(true);
  };

  const handleProcessingRestriction = async () => {
    setLoading(true);
    try {
      // Simulate API call to request processing restriction
      await new Promise(resolve => setTimeout(resolve, 2000));
      
      Alert.alert(
        'Processing Restriction Requested',
        'Your request to restrict data processing has been submitted. Our privacy team will review your request within 5 business days and contact you with the outcome.',
        [
          { text: 'OK', onPress: () => setShowDetailModal(false) }
        ]
      );
    } catch (error) {
      Alert.alert('Error', 'Failed to submit restriction request. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const handleObjection = async () => {
    setLoading(true);
    try {
      // Simulate API call to submit objection
      await new Promise(resolve => setTimeout(resolve, 2000));
      
      Alert.alert(
        'Objection Submitted',
        'Your objection has been submitted. We will review your objection and respond within 30 days. You will receive an email with our decision.',
        [
          { text: 'OK', onPress: () => setShowDetailModal(false) }
        ]
      );
    } catch (error) {
      Alert.alert('Error', 'Failed to submit objection. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const handleHumanReview = async () => {
    setLoading(true);
    try {
      // Simulate API call to request human review
      await new Promise(resolve => setTimeout(resolve, 2000));
      
      Alert.alert(
        'Human Review Requested',
        'Your request for human review has been submitted. Our team will review the automated decision and provide a response within 30 days.',
        [
          { text: 'OK', onPress: () => setShowDetailModal(false) }
        ]
      );
    } catch (error) {
      Alert.alert('Error', 'Failed to submit human review request. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const handleEmailDPO = () => {
    Linking.openURL('mailto:privacy@flipstar.et?subject=GDPR Rights Request');
  };

  const handleCallDPO = () => {
    Linking.openURL('tel:+251123456789');
  };

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()}>
          <Ionicons name="chevron-back" size={24} color="#fff" />
        </TouchableOpacity>
        <Text style={styles.title}>Your GDPR Rights</Text>
        <View style={{ width: 24 }} />
      </View>

      <ScrollView style={styles.content} showsVerticalScrollIndicator={false}>
        <View style={styles.introSection}>
          <Ionicons name="shield-checkmark" size={48} color="#8fc441" />
          <Text style={styles.introTitle}>Your Privacy Rights</Text>
          <Text style={styles.introDescription}>
            Under the General Data Protection Regulation (GDPR), you have the following rights regarding your personal data.
          </Text>
        </View>

        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Your Rights</Text>
          {rights.map((right, index) => (
            <TouchableOpacity 
              key={index} 
              style={styles.rightItem}
              onPress={() => handleRightPress(right)}
            >
              <View style={styles.rightIcon}>
                <Ionicons name={right.icon} size={24} color={right.color} />
              </View>
              <View style={styles.rightContent}>
                <Text style={styles.rightTitle}>{right.title}</Text>
                <Text style={styles.rightDescription}>{right.description}</Text>
                {right.action && (
                  <View style={styles.actionBadge}>
                    <Text style={styles.actionText}>Exercise Right</Text>
                  </View>
                )}
              </View>
              <Ionicons name="chevron-forward" size={20} color="#666" />
            </TouchableOpacity>
          ))}
        </View>

        <View style={styles.section}>
          <Text style={styles.sectionTitle}>How to Exercise Your Rights</Text>
          <View style={styles.stepsList}>
            <View style={styles.stepItem}>
              <View style={styles.stepNumber}>
                <Text style={styles.stepNumberText}>1</Text>
              </View>
              <Text style={styles.stepText}>
                Use the "Exercise Right" buttons above for direct actions
              </Text>
            </View>
            <View style={styles.stepItem}>
              <View style={styles.stepNumber}>
                <Text style={styles.stepNumberText}>2</Text>
              </View>
              <Text style={styles.stepText}>
                Contact our privacy team at privacy@flipstar.et
              </Text>
            </View>
            <View style={styles.stepItem}>
              <View style={styles.stepNumber}>
                <Text style={styles.stepNumberText}>3</Text>
              </View>
              <Text style={styles.stepText}>
                We'll respond within 30 days with an update
              </Text>
            </View>
          </View>
        </View>

        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Data Protection Officer</Text>
          <View style={styles.dpoCard}>
            <Ionicons name="person" size={32} color="#8fc441" />
            <View style={styles.dpoInfo}>
              <Text style={styles.dpoTitle}>Data Protection Officer</Text>
              <TouchableOpacity onPress={handleEmailDPO}>
                <Text style={styles.dpoEmail}>privacy@flipstar.et</Text>
              </TouchableOpacity>
              <TouchableOpacity onPress={handleCallDPO}>
                <Text style={styles.dpoPhone}>+251 123 456 789</Text>
              </TouchableOpacity>
              <Text style={styles.dpoAddress}>Addis Ababa, Ethiopia</Text>
              <View style={styles.dpoActions}>
                <TouchableOpacity style={styles.dpoButton} onPress={handleEmailDPO}>
                  <Ionicons name="mail" size={16} color="#fff" />
                  <Text style={styles.dpoButtonText}>Email</Text>
                </TouchableOpacity>
                <TouchableOpacity style={[styles.dpoButton, styles.dpoButtonSecondary]} onPress={handleCallDPO}>
                  <Ionicons name="call" size={16} color="#8fc441" />
                  <Text style={[styles.dpoButtonText, styles.dpoButtonTextSecondary]}>Call</Text>
                </TouchableOpacity>
              </View>
            </View>
          </View>
        </View>

        <View style={styles.section}>
          <Text style={styles.sectionTitle}>International Data Transfers</Text>
          <View style={styles.transferCard}>
            <Ionicons name="globe" size={24} color="#10B981" />
            <View style={styles.transferInfo}>
              <Text style={styles.transferTitle}>EU-U.S. Data Privacy Framework</Text>
              <Text style={styles.transferDescription}>
                We transfer data internationally using the EU-U.S. Data Privacy Framework, Standard Contractual Clauses, and other legally adequate mechanisms to ensure your data is protected.
              </Text>
            </View>
          </View>
        </View>

        <View style={styles.footer}>
          <Text style={styles.footerText}>
            For more information about your rights under GDPR, please visit our privacy policy or contact our Data Protection Officer.
          </Text>
        </View>
      </ScrollView>
      
      {/* Detailed Rights Modal */}
      <Modal
        visible={showDetailModal}
        transparent={true}
        animationType="fade"
        onRequestClose={() => setShowDetailModal(false)}
      >
        <View style={styles.modalOverlay}>
          <View style={styles.modalContainer}>
            <View style={styles.modalHeader}>
              {selectedRight && (
                <Ionicons name={selectedRight.icon} size={32} color={selectedRight.color} />
              )}
              <Text style={styles.modalTitle}>
                {selectedRight?.title}
              </Text>
              <TouchableOpacity onPress={() => setShowDetailModal(false)}>
                <Ionicons name="close" size={24} color="#666" />
              </TouchableOpacity>
            </View>
            
            <ScrollView style={styles.modalContent} showsVerticalScrollIndicator={false}>
              <Text style={styles.modalDescription}>
                {selectedRight?.description}
              </Text>
              
              <Text style={styles.modalDetails}>
                {selectedRight?.details}
              </Text>
              
              {selectedRight?.legalBasis && (
                <View style={styles.modalSection}>
                  <Text style={styles.modalSectionTitle}>Legal Basis</Text>
                  <Text style={styles.modalSectionText}>
                    {selectedRight.legalBasis}
                  </Text>
                </View>
              )}
              
              {selectedRight?.dataTypes && (
                <View style={styles.modalSection}>
                  <Text style={styles.modalSectionTitle}>Data Types</Text>
                  <Text style={styles.modalSectionText}>
                    {selectedRight.dataTypes}
                  </Text>
                </View>
              )}
              
              {selectedRight?.procedure && (
                <View style={styles.modalSection}>
                  <Text style={styles.modalSectionTitle}>Procedure</Text>
                  <Text style={styles.modalSectionText}>
                    {selectedRight.procedure}
                  </Text>
                </View>
              )}
              
              {selectedRight?.exceptions && (
                <View style={styles.modalSection}>
                  <Text style={styles.modalSectionTitle}>Exceptions</Text>
                  <Text style={styles.modalSectionText}>
                    {selectedRight.exceptions}
                  </Text>
                </View>
              )}
              
              <View style={styles.modalActions}>
                <TouchableOpacity 
                  style={styles.modalButton} 
                  onPress={() => setShowDetailModal(false)}
                >
                  <Text style={styles.modalButtonText}>Close</Text>
                </TouchableOpacity>
                
                {selectedRight?.action && (
                  <TouchableOpacity 
                    style={[styles.modalButton, styles.modalButtonPrimary]}
                    onPress={() => {
                      setShowDetailModal(false);
                      handleRightAction(selectedRight.action);
                    }}
                    disabled={loading}
                  >
                    {loading ? (
                      <Text style={styles.modalButtonText}>Processing...</Text>
                    ) : (
                      <Text style={styles.modalButtonText}>Exercise Right</Text>
                    )}
                  </TouchableOpacity>
                )}
              </View>
            </ScrollView>
          </View>
        </View>
      </Modal>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#0D0D0D',
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: 20,
    paddingTop: 60,
    borderBottomWidth: 1,
    borderBottomColor: '#262626',
  },
  title: {
    color: '#fff',
    fontSize: 20,
    fontWeight: '600',
  },
  content: {
    flex: 1,
    padding: 20,
  },
  introSection: {
    alignItems: 'center',
    marginBottom: 32,
  },
  introTitle: {
    color: '#fff',
    fontSize: 24,
    fontWeight: 'bold',
    marginTop: 16,
    marginBottom: 8,
  },
  introDescription: {
    color: '#888',
    fontSize: 16,
    textAlign: 'center',
    lineHeight: 24,
  },
  section: {
    marginBottom: 32,
  },
  sectionTitle: {
    color: '#fff',
    fontSize: 20,
    fontWeight: '600',
    marginBottom: 16,
  },
  rightItem: {
    backgroundColor: '#1A1A1A',
    padding: 16,
    borderRadius: 12,
    marginBottom: 12,
    borderWidth: 1,
    borderColor: '#262626',
    flexDirection: 'row',
    alignItems: 'center',
  },
  rightIcon: {
    width: 48,
    height: 48,
    borderRadius: 24,
    backgroundColor: '#262626',
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 16,
  },
  rightContent: {
    flex: 1,
  },
  rightTitle: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
    marginBottom: 4,
  },
  rightDescription: {
    color: '#888',
    fontSize: 14,
    lineHeight: 20,
    marginBottom: 8,
  },
  actionBadge: {
    backgroundColor: '#8fc441',
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 4,
    alignSelf: 'flex-start',
  },
  actionText: {
    color: '#fff',
    fontSize: 12,
    fontWeight: '600',
  },
  stepsList: {
    backgroundColor: '#1A1A1A',
    borderRadius: 12,
    padding: 16,
    borderWidth: 1,
    borderColor: '#262626',
  },
  stepItem: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 16,
  },
  stepNumber: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: '#8fc441',
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 16,
  },
  stepNumberText: {
    color: '#fff',
    fontSize: 14,
    fontWeight: '600',
  },
  stepText: {
    color: '#ccc',
    fontSize: 14,
    lineHeight: 20,
    flex: 1,
  },
  dpoCard: {
    backgroundColor: '#1A1A1A',
    borderRadius: 12,
    padding: 16,
    borderWidth: 1,
    borderColor: '#262626',
    flexDirection: 'row',
    alignItems: 'center',
  },
  dpoInfo: {
    marginLeft: 16,
  },
  dpoTitle: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
    marginBottom: 4,
  },
  dpoEmail: {
    color: '#8fc441',
    fontSize: 14,
    marginBottom: 2,
  },
  dpoPhone: {
    color: '#ccc',
    fontSize: 14,
    marginBottom: 2,
  },
  dpoAddress: {
    color: '#888',
    fontSize: 12,
  },
  transferCard: {
    backgroundColor: '#1A1A1A',
    borderRadius: 12,
    padding: 16,
    borderWidth: 1,
    borderColor: '#262626',
    flexDirection: 'row',
    alignItems: 'center',
  },
  transferInfo: {
    marginLeft: 16,
    flex: 1,
  },
  transferTitle: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
    marginBottom: 4,
  },
  transferDescription: {
    color: '#888',
    fontSize: 14,
    lineHeight: 20,
  },
  footer: {
    padding: 20,
    borderTopWidth: 1,
    borderTopColor: '#262626',
  },
  footerText: {
    color: '#666',
    fontSize: 12,
    textAlign: 'center',
    lineHeight: 18,
  },
  // Modal styles
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.7)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  modalContainer: {
    backgroundColor: '#1A1A1A',
    borderRadius: 20,
    width: '90%',
    maxWidth: 400,
    maxHeight: '80%',
  },
  modalHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: 20,
    borderBottomWidth: 1,
    borderBottomColor: '#262626',
  },
  modalTitle: {
    color: '#fff',
    fontSize: 18,
    fontWeight: '600',
    flex: 1,
    textAlign: 'center',
  },
  modalContent: {
    padding: 20,
  },
  modalDescription: {
    color: '#ccc',
    fontSize: 16,
    fontWeight: '600',
    marginBottom: 12,
  },
  modalDetails: {
    color: '#888',
    fontSize: 14,
    lineHeight: 20,
    marginBottom: 20,
  },
  modalSection: {
    backgroundColor: '#0D0D0D',
    borderRadius: 8,
    padding: 12,
    marginBottom: 16,
  },
  modalSectionTitle: {
    color: '#8fc441',
    fontSize: 14,
    fontWeight: '600',
    marginBottom: 4,
  },
  modalSectionText: {
    color: '#ccc',
    fontSize: 13,
    lineHeight: 18,
  },
  modalActions: {
    flexDirection: 'row',
    gap: 12,
    marginTop: 20,
  },
  modalButton: {
    flex: 1,
    backgroundColor: '#333',
    paddingVertical: 12,
    paddingHorizontal: 20,
    borderRadius: 8,
    alignItems: 'center',
  },
  modalButtonPrimary: {
    backgroundColor: '#8fc441',
  },
  modalButtonText: {
    color: '#fff',
    fontSize: 14,
    fontWeight: '600',
  },
  // DPO interaction styles
  dpoActions: {
    flexDirection: 'row',
    gap: 12,
    marginTop: 12,
  },
  dpoButton: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#8fc441',
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: 6,
    gap: 6,
  },
  dpoButtonSecondary: {
    backgroundColor: 'transparent',
    borderWidth: 1,
    borderColor: '#8fc441',
  },
  dpoButtonText: {
    color: '#fff',
    fontSize: 12,
    fontWeight: '600',
  },
  dpoButtonTextSecondary: {
    color: '#8fc441',
  },
});

export default EURightsScreen;
