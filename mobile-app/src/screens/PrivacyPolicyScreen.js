import React from 'react';
import { View, Text, ScrollView, StyleSheet, Linking, TouchableOpacity } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

const PrivacyPolicyScreen = ({ navigation }) => {
  const privacyPolicyContent = `# FlipStar Privacy Policy

**Last Updated:** May 22, 2026  
**Effective Date:** May 22, 2026

## 1. Developer Information

**Company:** SkykinTechnologies PLC  
**Contact:** privacy@flipstar.et  
**Website:** https://flipstar.et  

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
- Website: https://flipstar.et

## 12. Account Deletion

You can delete your account at any time through:
- The app settings menu
- Our website at flipstar.et/delete-account
- Contacting our support team

When you delete your account, we will permanently delete your personal information within 30 days, except where we are required by law to retain certain data.`;

  const handleContactEmail = () => {
    Linking.openURL('mailto:privacy@flipstar.et');
  };

  const handleWebsite = () => {
    Linking.openURL('https://flipstar.et');
  };

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()}>
          <Ionicons name="chevron-back" size={24} color="#fff" />
        </TouchableOpacity>
        <Text style={styles.title}>Privacy Policy</Text>
        <View style={{ width: 24 }} />
      </View>

      <ScrollView style={styles.content} showsVerticalScrollIndicator={false}>
        <Text style={styles.policyText}>{privacyPolicyContent}</Text>

        <View style={styles.contactSection}>
          <Text style={styles.contactTitle}>Need Help?</Text>
          <Text style={styles.contactDescription}>
            If you have questions about this privacy policy or need to exercise your data rights, we're here to help.
          </Text>
          
          <TouchableOpacity style={styles.contactButton} onPress={handleContactEmail}>
            <Ionicons name="mail" size={20} color="#fff" />
            <Text style={styles.contactButtonText}>Email Privacy Team</Text>
          </TouchableOpacity>
          
          <TouchableOpacity style={styles.websiteButton} onPress={handleWebsite}>
            <Ionicons name="globe" size={20} color="#8fc441" />
            <Text style={styles.websiteButtonText}>Visit Our Website</Text>
          </TouchableOpacity>
        </View>

        <View style={styles.footer}>
          <Text style={styles.footerText}>
            This privacy policy is part of our commitment to transparency and user privacy.
          </Text>
          <Text style={styles.footerText}>
            Last updated: May 22, 2026
          </Text>
        </View>
      </ScrollView>
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
  policyText: {
    color: '#ccc',
    fontSize: 14,
    lineHeight: 22,
    fontFamily: 'monospace',
  },
  contactSection: {
    backgroundColor: '#1A1A1A',
    borderRadius: 12,
    padding: 20,
    margin: 20,
    borderWidth: 1,
    borderColor: '#262626',
  },
  contactTitle: {
    color: '#fff',
    fontSize: 18,
    fontWeight: '600',
    marginBottom: 8,
  },
  contactDescription: {
    color: '#888',
    fontSize: 14,
    lineHeight: 20,
    marginBottom: 20,
  },
  contactButton: {
    backgroundColor: '#3B82F6',
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    padding: 16,
    borderRadius: 8,
    marginBottom: 12,
    gap: 8,
  },
  contactButtonText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
  },
  websiteButton: {
    backgroundColor: '#1A1A1A',
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    padding: 16,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#8fc441',
    gap: 8,
  },
  websiteButtonText: {
    color: '#8fc441',
    fontSize: 16,
    fontWeight: '600',
  },
  footer: {
    padding: 20,
    alignItems: 'center',
  },
  footerText: {
    color: '#666',
    fontSize: 12,
    textAlign: 'center',
    marginBottom: 4,
  },
});

export default PrivacyPolicyScreen;
