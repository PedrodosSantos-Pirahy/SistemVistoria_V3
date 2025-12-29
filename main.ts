import { bootstrapApplication } from '@angular/platform-browser';
import { provideRouter } from '@angular/router';
import { AppComponent } from './src/app.component';
import { APP_ROUTES } from './src/app.routing.module';

bootstrapApplication(AppComponent, {
  providers: [
    provideRouter(APP_ROUTES)
  ]
}).catch(err => console.error(err));
