import { bootstrapApplication } from '@angular/platform-browser';
import { provideHttpClient } from '@angular/common/http';
import { provideRouter, withHashLocation } from '@angular/router';

// SEUS ARQUIVOS ESTÃO NA MESMA PASTA (src), ENTÃO É APENAS ./
import { AppComponent } from './app.component'; 
import { APP_ROUTES } from './app.routing.module';

bootstrapApplication(AppComponent, {
  providers: [
    provideHttpClient(),
    provideRouter(APP_ROUTES, withHashLocation()) 
  ]
}).catch(err => console.error(err));