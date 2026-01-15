import { Component } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { CodeInputComponent } from './components/code-input/code-input';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [RouterOutlet, CodeInputComponent],
  templateUrl: './app.html',
  styleUrls: ['./app.css'],
})
export class App {}
