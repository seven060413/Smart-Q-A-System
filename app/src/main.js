import {
	createSSRApp
} from "vue";
import App from "./App.vue";
import ThemeBackground from "./components/theme-background/theme-background.vue";
export function createApp() {
	const app = createSSRApp(App);
	app.component('ThemeBackground', ThemeBackground);
	return {
		app,
	};
}
