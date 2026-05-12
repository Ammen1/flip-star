import React, { createContext, useContext, useState, useEffect } from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';

const LanguageContext = createContext();

export const useLanguage = () => {
  const context = useContext(LanguageContext);
  if (!context) {
    throw new Error('useLanguage must be used within a LanguageProvider');
  }
  return context;
};

// Translation dictionary
const translations = {
  en: {
    settings: 'Settings',
    account: 'Account',
    notifications: 'Notifications',
    privacy: 'Privacy',
    appearance: 'Appearance',
    help: 'Help',
    darkMode: 'Dark Mode',
    language: 'Language',
    editProfile: 'Edit Profile',
    wallet: 'Wallet',
    subscription: 'Subscription',
    changePassword: 'Change Password',
    downloadData: 'Download Data',
    likes: 'Likes',
    comments: 'Comments',
    follows: 'Follows',
    messages: 'Messages',
    privateAccount: 'Private Account',
    showActivity: 'Show Activity',
    allowMessages: 'Allow Messages',
    resetSuggestions: 'Reset Suggested Content',
    helpCenter: 'Help Center',
    privacyPolicy: 'Privacy Policy',
    termsOfService: 'Terms of Service',
    blockedUsers: 'Blocked Users',
    dangerZone: 'Danger Zone',
    deleteAccount: 'Delete Account',
    logout: 'Logout',
    chooseLanguage: 'Choose Language',
    currentPassword: 'Current Password',
    newPassword: 'New Password',
    confirmNewPassword: 'Confirm New Password',
    updatePassword: 'Update Password',
    english: 'English',
    amharic: 'አማርኛ (Amharic)',
    spanish: 'Español',
    french: 'Français',
    arabic: 'العربية',
  },
  am: {
    settings: 'ቅንብሮች',
    account: 'መለያ',
    notifications: 'ማስታወቂያዎች',
    privacy: 'የግላዊነት',
    appearance: 'አልባም',
    help: 'እርዳታ',
    darkMode: 'ጨለማ ዘዴ',
    language: 'ቋንቋ',
    editProfile: 'መለያ ማረም',
    wallet: 'የገንዘብ ቦርሳ',
    subscription: 'የመዝገብ ክፍያ',
    changePassword: 'የይለፍ ቃል መቀየር',
    downloadData: 'ዳታ ማውጣት',
    likes: 'የሚወዱ',
    comments: 'አስተያየት',
    follows: 'እየከነበሩ',
    messages: 'መልእክቶች',
    privateAccount: 'የግላዊ መለያ',
    showActivity: 'እንቅናት አሳይ',
    allowMessages: 'መልእክቶች ፍቀድ',
    resetSuggestions: 'የተገለጉ አስታዋቾችን እንደገና ማስጀመር',
    helpCenter: 'የእርዳታ ማእከል',
    privacyPolicy: 'የግላዊነት ፖሊሲ',
    termsOfService: 'የአገልግሎት ውልደታ',
    blockedUsers: 'የተከሉት ተጠቃሚዎች',
    dangerZone: 'የአደጋ ሜዳ',
    deleteAccount: 'መለያ መሰረዝ',
    logout: 'መውጣት',
    chooseLanguage: 'ቋንቋ ይምረጡ',
    currentPassword: 'የአሁኑ የይለፍ ቃል',
    newPassword: 'አዲስ የይለፍ ቃል',
    confirmNewPassword: 'አዲስ የይለፍ ቃል ያረጋግጡ',
    updatePassword: 'የይለፍ ቃል ያሻሽሉ',
    english: 'English',
    amharic: 'አማርኛ',
    spanish: 'Español',
    french: 'Français',
    arabic: 'العربية',
  },
  es: {
    settings: 'Configuración',
    account: 'Cuenta',
    notifications: 'Notificaciones',
    privacy: 'Privacidad',
    appearance: 'Apariencia',
    help: 'Ayuda',
    darkMode: 'Modo Oscuro',
    language: 'Idioma',
    editProfile: 'Editar Perfil',
    wallet: 'Billetera',
    subscription: 'Suscripción',
    changePassword: 'Cambiar Contraseña',
    downloadData: 'Descargar Datos',
    likes: 'Me Gusta',
    comments: 'Comentarios',
    follows: 'Seguidores',
    messages: 'Mensajes',
    privateAccount: 'Cuenta Privada',
    showActivity: 'Mostrar Actividad',
    allowMessages: 'Permitir Mensajes',
    resetSuggestions: 'Restablecer Sugerencias',
    helpCenter: 'Centro de Ayuda',
    privacyPolicy: 'Política de Privacidad',
    termsOfService: 'Términos de Servicio',
    blockedUsers: 'Usuarios Bloqueados',
    dangerZone: 'Zona de Peligro',
    deleteAccount: 'Eliminar Cuenta',
    logout: 'Cerrar Sesión',
    chooseLanguage: 'Elegir Idioma',
    currentPassword: 'Contraseña Actual',
    newPassword: 'Nueva Contraseña',
    confirmNewPassword: 'Confirmar Nueva Contraseña',
    updatePassword: 'Actualizar Contraseña',
    english: 'English',
    amharic: 'አማርኛ (Amharic)',
    spanish: 'Español',
    french: 'Français',
    arabic: 'العربية',
  },
  fr: {
    settings: 'Paramètres',
    account: 'Compte',
    notifications: 'Notifications',
    privacy: 'Confidentialité',
    appearance: 'Apparence',
    help: 'Aide',
    darkMode: 'Mode Sombre',
    language: 'Langue',
    editProfile: 'Modifier le Profil',
    wallet: 'Portefeuille',
    subscription: 'Abonnement',
    changePassword: 'Changer le Mot de Passe',
    downloadData: 'Télécharger les Données',
    likes: 'J\'aime',
    comments: 'Commentaires',
    follows: 'Abonnés',
    messages: 'Messages',
    privateAccount: 'Compte Privé',
    showActivity: 'Afficher l\'Activité',
    allowMessages: 'Autoriser les Messages',
    resetSuggestions: 'Réinitialiser les Suggestions',
    helpCenter: 'Centre d\'Aide',
    privacyPolicy: 'Politique de Confidentialité',
    termsOfService: 'Conditions d\'Utilisation',
    blockedUsers: 'Utilisateurs Bloqués',
    dangerZone: 'Zone de Danger',
    deleteAccount: 'Supprimer le Compte',
    logout: 'Déconnexion',
    chooseLanguage: 'Choisir la Langue',
    currentPassword: 'Mot de Passe Actuel',
    newPassword: 'Nouveau Mot de Passe',
    confirmNewPassword: 'Confirmer le Nouveau Mot de Passe',
    updatePassword: 'Mettre à Jour le Mot de Passe',
    english: 'English',
    amharic: 'አማርኛ (Amharic)',
    spanish: 'Español',
    french: 'Français',
    arabic: 'العربية',
  },
  ar: {
    settings: 'الإعدادات',
    account: 'الحساب',
    notifications: 'الإشعارات',
    privacy: 'الخصوصية',
    appearance: 'المظهر',
    help: 'المساعدة',
    darkMode: 'الوضع الليلي',
    language: 'اللغة',
    editProfile: 'تعديل الملف الشخصي',
    wallet: 'المحفظة',
    subscription: 'الاشتراك',
    changePassword: 'تغيير كلمة المرور',
    downloadData: 'تنزيل البيانات',
    likes: 'الإعجابات',
    comments: 'التعليقات',
    follows: 'المتابعون',
    messages: 'الرسائل',
    privateAccount: 'حساب خاص',
    showActivity: 'إظهار النشاط',
    allowMessages: 'السماح بالرسائل',
    resetSuggestions: 'إعادة تعيين الاقتراحات',
    helpCenter: 'مركز المساعدة',
    privacyPolicy: 'سياسة الخصوصية',
    termsOfService: 'شروط الخدمة',
    blockedUsers: 'المستخدمون المحظورون',
    dangerZone: 'منطقة الخطر',
    deleteAccount: 'حذف الحساب',
    logout: 'تسجيل الخروج',
    chooseLanguage: 'اختر اللغة',
    currentPassword: 'كلمة المرور الحالية',
    newPassword: 'كلمة مرور جديدة',
    confirmNewPassword: 'تأكيد كلمة المرور الجديدة',
    updatePassword: 'تحديث كلمة المرور',
    english: 'English',
    amharic: 'አማርኛ (Amharic)',
    spanish: 'Español',
    french: 'Français',
    arabic: 'العربية',
  }
};

export const LanguageProvider = ({ children }) => {
  const [language, setLanguageState] = useState('en');

  const setLanguage = async (lang) => {
    setLanguageState(lang);
    try {
      await AsyncStorage.setItem('language', lang);
    } catch (error) {
      console.error('Failed to save language setting:', error);
    }
  };

  const t = (key) => {
    return translations[language]?.[key] || translations.en[key] || key;
  };

  // Load language preference on mount
  useEffect(() => {
    const loadLanguage = async () => {
      try {
        const saved = await AsyncStorage.getItem('language');
        if (saved) {
          setLanguageState(saved);
        }
      } catch (error) {
        console.error('Failed to load language setting:', error);
      }
    };
    loadLanguage();
  }, []);

  const value = {
    language,
    setLanguage,
    t,
    translations: translations[language] || translations.en
  };

  return (
    <LanguageContext.Provider value={value}>
      {children}
    </LanguageContext.Provider>
  );
};
