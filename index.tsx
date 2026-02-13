import { bootstrapApplication } from '@angular/platform-browser';
import { provideZonelessChangeDetection, isDevMode } from '@angular/core';
import { AppComponent } from './src/app.component';
import { provideServiceWorker } from '@angular/service-worker';

bootstrapApplication(AppComponent, {
  providers: [
    provideZonelessChangeDetection(),
    // Mantenha apenas uma vez:
    provideServiceWorker('ngsw-worker.js', {
      enabled: !isDevMode(), // Em produção ativa, em dev desativa
      registrationStrategy: 'registerWhenStable:30000'
    })
  ],
}).catch(err => console.error(err));