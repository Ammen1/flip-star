import { createContext, useContext, useState, useEffect } from 'react';

const LanguageContext = createContext();

export const useLanguage = () => {
  const context = useContext(LanguageContext);
  if (!context) {
    throw new Error('useLanguage must be used within LanguageProvider');
  }
  return context;
};

const translations = {
  en: {
    // Navigation
    home: "Home",
    forYou: "For You",
    search: "Search",
    explore: "Explore",
    reels: "Reels",
    followingTab: "Following",
    inbox: "Inbox",
    messages: "Messages",
    notifications: "Notifications",
    bookmarks: "Bookmarks",
    create: "Create",
    profile: "Profile",
    settings: "Settings",
    logout: "Logout",
    login: "Login",
    signUp: "Sign Up",
    campaigns: "Campaigns",
    winners: "Winners",
    suggestions: "Suggestions",
    recommended: "Recommended for You",

    // Actions
    like: "Like",
    comment: "Comment",
    share: "Share",
    save: "Save",
    saved: "Saved",
    follow: "Follow",
    following: "Following",
    unfollow: "Unfollow",
    edit: "Edit",
    delete: "Delete",
    cancel: "Cancel",
    confirm: "Confirm",
    ok: "OK",
    post: "Post",
    send: "Send",
    next: "Next",
    back: "Back",
    submit: "Submit",
    retry: "Retry",
    close: "Close",
    refresh: "Refresh",

    // Profile
    posts: "Posts",
    followers: "Followers",
    followingCount: "Following",
    editProfile: "Edit Profile",
    bio: "Bio",
    photo: "Photo",

    // Wallet
    wallet: "Wallet",
    coins: "Coins",
    points: "Points",
    totalBalance: "Total Balance",
    earned: "Earned",
    purchased: "Purchased",
    buyCoins: "Buy Coins",
    withdraw: "Withdraw",
    withdrawToBirr: "Points → Birr",
    recentActivity: "Recent Activity",
    overview: "Overview",
    transactions: "Transactions",
    withdrawals: "Withdrawals",

    // Subscription
    subscription: "Subscription",
    plansAndBilling: "Plans & billing",

    // Settings
    account: "Account",
    accountSettings: "Account Settings",
    manageAccount: "Manage your account information",
    notificationsSettings: "Notifications",
    manageNotifications: "Manage your notification preferences",
    privacy: "Privacy & Security",
    controlPrivacy: "Control your privacy settings",
    appearance: "Appearance",
    customizeAppearance: "Customize how FlipStar looks",
    language: "Language",
    chooseLanguage: "Choose your preferred language",
    help: "Help & Support",
    getHelp: "Get help and support",
    darkMode: "Dark Mode",
    changePassword: "Change Password",
    currentPassword: "Current Password",
    newPassword: "New Password (6 digits)",
    confirmPassword: "Confirm New Password",
    updatePassword: "Update Password",
    downloadData: "Download Your Data",
    downloadDataDesc: "Download a copy of all your posts, comments, and profile data",
    deleteAccount: "Delete Account",
    dangerZone: "Danger Zone",
    deleteWarning: "Once you delete your account, there is no going back. Please be certain.",
    basicInfo: "Basic Information",
    username: "Username",
    email: "Email",
    phoneNumber: "Phone Number",
    dataManagement: "Data Management",
    success: "Success",
    settingsSaved: "Settings saved successfully!",
    error: "Error",
    passwordMismatch: "New passwords do not match!",
    passwordTooShort: "Password must be at least 6 digits!",
    passwordChanged: "Password changed successfully!",
    passwordChangeFailed: "Failed to change password",
    deleteConfirm: "Are you sure you want to delete your account? This action cannot be undone!",
    finalConfirm: "This will permanently delete all your data. Are you absolutely sure?",
    accountDeleted: "Account Deleted",
    accountDeleting: "Account deletion initiated. You will be logged out.",
    downloadInitiated: "Download Initiated",
    downloadEmail: "Your data download has been initiated. You will receive an email with a download link.",
    notificationEnabled: "Notification Enabled",
    willReceive: "You will now receive notifications for",
    privacyUpdated: "Privacy Updated",
    privacySettingChanged: "Privacy setting",
    enabled: "has been enabled",
    disabled: "has been disabled",
    darkEnabled: "Dark theme enabled",
    lightEnabled: "Light theme enabled",
    receiveNotifications: "Receive notifications for",
    privateAccountDesc: "Only approved followers can see your posts",
    showActivityDesc: "Show your activity status to others",
    allowMessagesDesc: "Allow others to send you messages",
    helpCenter: "Help Center",
    reportProblem: "Report a Problem",
    termsOfService: "Terms of Service",
    privacyPolicy: "Privacy Policy",
    version: "Version",
    likes: "Likes",
    comments: "Comments",
    follows: "Follows",

    // Post
    caption: "Caption",
    hashtags: "Hashtags",
    uploadMedia: "Upload Media",

    // Common
    loading: "Loading...",
    noResults: "No results found",
  },
  am: {
    // Navigation
    home: "መነሻ",
    forYou: "ለእርስዎ",
    search: "ፈልግ",
    explore: "ያስሱ",
    reels: "ሪልስ",
    followingTab: "እየተከተሉ",
    inbox: "መልዕክቶች",
    messages: "መልዕክቶች",
    notifications: "ማሳወቂያዎች",
    bookmarks: "የተቀመጡ",
    create: "ይፍጠሩ",
    profile: "መገለጫ",
    settings: "ቅንብሮች",
    logout: "ውጣ",
    login: "ግባ",
    signUp: "ይመዝገቡ",
    campaigns: "ዘመቻዎች",
    winners: "አሸናፊዎች",
    suggestions: "ጥቆማዎች",
    recommended: "ለእርስዎ የሚመከር",

    // Actions
    like: "ይወዱ",
    comment: "አስተያየት",
    share: "አጋራ",
    save: "አስቀምጥ",
    saved: "ተቀምጧል",
    follow: "ተከተል",
    following: "እየተከተሉ",
    unfollow: "አትከተል",
    edit: "አርትዕ",
    delete: "ሰርዝ",
    cancel: "ይቅር",
    confirm: "አረጋግጥ",
    ok: "እሺ",
    post: "ለጥፍ",
    send: "ላክ",
    next: "ቀጥል",
    back: "ተመለስ",
    submit: "አስገባ",
    retry: "እንደገና ሞክር",
    close: "ዝጋ",
    refresh: "አድስ",

    // Profile
    posts: "ልጥፎች",
    followers: "ተከታዮች",
    followingCount: "እየተከተሉ",
    editProfile: "መገለጫ አርትዕ",
    bio: "ስለ እኔ",
    photo: "ፎቶ",

    // Wallet
    wallet: "ቦርሳ",
    coins: "ሳንቲሞች",
    points: "ነጥቦች",
    totalBalance: "ጠቅላላ ቀሪ",
    earned: "የተገኘ",
    purchased: "የተገዛ",
    buyCoins: "ሳንቲም ግዛ",
    withdraw: "ውጣ",
    withdrawToBirr: "ነጥብ → ብር",
    recentActivity: "የቅርብ ጊዜ እንቅስቃሴ",
    overview: "አጠቃላይ እይታ",
    transactions: "ግብይቶች",
    withdrawals: "ውጣዎች",

    // Subscription
    subscription: "የደንበኝነት ምዝገባ",
    plansAndBilling: "ዕቅዶች እና ክፍያ",

    // Settings
    account: "መለያ",
    accountSettings: "የመለያ ቅንብሮች",
    manageAccount: "የመለያ መረጃዎን ያስተዳድሩ",
    notificationsSettings: "ማሳወቂያዎች",
    manageNotifications: "የማሳወቂያ ምርጫዎችዎን ያስተዳድሩ",
    privacy: "ግላዊነት እና ደህንነት",
    controlPrivacy: "የግላዊነት ቅንብሮችዎን ይቆጣጠሩ",
    appearance: "መልክ",
    customizeAppearance: "FlipStar እንዴት እንደሚታይ ያቀናብሩ",
    language: "ቋንቋ",
    chooseLanguage: "የሚፈልጉትን ቋንቋ ይምረጡ",
    help: "እገዛ እና ድጋፍ",
    getHelp: "እገዛ እና ድጋፍ ያግኙ",
    darkMode: "ጨለማ ሁነታ",
    changePassword: "የይለፍ ቃል ቀይር",
    currentPassword: "አሁን ያለው የይለፍ ቃል",
    newPassword: "አዲስ የይለፍ ቃል (6 ቁጥሮች)",
    confirmPassword: "አዲሱን የይለፍ ቃል ያረጋግጡ",
    updatePassword: "የይለፍ ቃል ያዘምኑ",
    downloadData: "መረጃዎን ያውርዱ",
    downloadDataDesc: "ሁሉንም ልጥፎችዎን፣ አስተያየቶችን እና የመገለጫ መረጃዎን ይውርዱ",
    deleteAccount: "መለያ ሰርዝ",
    dangerZone: "የአደጋ ቀጠና",
    deleteWarning: "መለያዎን ካስወገዱ መመለስ አይቻልም። እባክዎ እርግጠኛ ይሁኑ።",
    basicInfo: "መሰረታዊ መረጃ",
    username: "የተጠቃሚ ስም",
    email: "ኢሜይል",
    phoneNumber: "ስልክ ቁጥር",
    dataManagement: "የመረጃ አስተዳደር",
    success: "ተሳክቷል",
    settingsSaved: "ቅንብሮች በተሳካ ሁኔታ ተቀምጠዋል!",
    error: "ስህተት",
    passwordMismatch: "አዲሶቹ የይለፍ ቃሎች አይዛመዱም!",
    passwordTooShort: "የይለፍ ቃል ቢያንስ 6 ቁጥሮች መሆን አለበት!",
    passwordChanged: "የይለፍ ቃል በተሳካ ሁኔታ ተቀይሯል!",
    passwordChangeFailed: "የይለፍ ቃል መቀየር አልተሳካም",
    deleteConfirm: "መለያዎን ለመሰረዝ እርግጠኛ ነዎት? ይህ ድርጊት መቀልበስ አይቻልም!",
    finalConfirm: "ይህ ሁሉንም መረጃዎን በቋሚነት ያጠፋል። በእርግጥ እርግጠኛ ነዎት?",
    accountDeleted: "መለያ ተሰርዟል",
    accountDeleting: "የመለያ ስረዛ ተጀምሯል። ይወጣሉ።",
    downloadInitiated: "ውርድ ተጀምሯል",
    downloadEmail: "የመረጃ ውርድዎ ተጀምሯል። የውርድ አገናኝ ያለው ኢሜይል ይደርስዎታል።",
    notificationEnabled: "ማሳወቂያ ነቅቷል",
    willReceive: "አሁን ለዚህ ማሳወቂያ ይደርስዎታል",
    privacyUpdated: "ግላዊነት ተዘምኗል",
    privacySettingChanged: "የግላዊነት ቅንብር",
    enabled: "ነቅቷል",
    disabled: "ተሰናክሏል",
    darkEnabled: "ጨለማ ገጽታ ነቅቷል",
    lightEnabled: "ብርሃን ገጽታ ነቅቷል",
    receiveNotifications: "ለዚህ ማሳወቂያ ይቀበሉ",
    privateAccountDesc: "የተፈቀዱ ተከታዮች ብቻ ልጥፎችዎን ማየት ይችላሉ",
    showActivityDesc: "የእንቅስቃሴ ሁኔታዎን ለሌሎች አሳይ",
    allowMessagesDesc: "ሌሎች መልዕክት እንዲልኩልዎ ፍቀዱ",
    helpCenter: "የእገዛ ማዕከል",
    reportProblem: "ችግር ሪፖርት ያድርጉ",
    termsOfService: "የአገልግሎት ውሎች",
    privacyPolicy: "የግላዊነት ፖሊሲ",
    version: "ስሪት",
    likes: "ውዶታዎች",
    comments: "አስተያየቶች",
    follows: "ተከታዮች",

    // Post
    caption: "መግለጫ",
    hashtags: "ሃሽታጎች",
    uploadMedia: "ሚዲያ ይስቀሉ",

    // Common
    loading: "በመጫን ላይ...",
    noResults: "ምንም ውጤት አልተገኘም",
  },
};

export const LanguageProvider = ({ children }) => {
  const [language, setLanguage] = useState(() => {
    const saved = localStorage.getItem('language');
    // Only allow en or am; migrate other stored values to en
    return saved && translations[saved] ? saved : 'en';
  });

  useEffect(() => {
    localStorage.setItem('language', language);
    document.documentElement.dir = 'ltr';
    document.documentElement.lang = language;
  }, [language]);

  const t = (key) => {
    return translations[language]?.[key] || translations.en[key] || key;
  };

  const changeLanguage = (lang) => {
    if (translations[lang]) {
      setLanguage(lang);
    }
  };

  return (
    <LanguageContext.Provider value={{ language, changeLanguage, t }}>
      {children}
    </LanguageContext.Provider>
  );
};
