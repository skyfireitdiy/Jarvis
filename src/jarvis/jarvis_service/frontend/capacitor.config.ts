import type { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'app.jarvis.mobile',
  appName: 'Jarvis',
  webDir: 'dist',
  server: {
    androidScheme: 'https'
  }
};

export default config;
