//
//  LoginView.swift
//  Travell Buddy
//
//  Main login screen with Apple, Google, and Email authentication options.
//

import SwiftUI
import AuthenticationServices

struct LoginView: View {
    @StateObject private var authManager = AuthManager.shared
    @State private var showEmailAuth = false

    var body: some View {
        ZStack {
            // Background
            LinearGradient(
                colors: [
                    Color(red: 45/255, green: 35/255, blue: 25/255),
                    Color(red: 30/255, green: 25/255, blue: 20/255),
                    Color(red: 0.06, green: 0.06, blue: 0.07)
                ],
                startPoint: .top,
                endPoint: .bottom
            )
            .ignoresSafeArea()

            VStack(spacing: 0) {
                Spacer()

                // Logo and tagline
                VStack(spacing: 16) {
                    Image(systemName: "airplane.departure")
                        .font(.system(size: 64, weight: .medium))
                        .foregroundColor(.travelBuddyOrange)

                    Text("Travel Buddy")
                        .font(.system(size: 32, weight: .bold))
                        .foregroundColor(.white)

                    Text("Ваш умный попутчик\nдля незабываемых путешествий")
                        .font(.system(size: 15))
                        .foregroundColor(.gray)
                        .multilineTextAlignment(.center)
                        .lineSpacing(4)
                }
                .padding(.bottom, 48)

                Spacer()

                // Auth buttons
                VStack(spacing: 12) {
                    // Sign in with Apple
                    AppleSignInButton()

                    // Sign in with Google
                    GoogleSignInButton()

                    // Sign in with Email
                    Button {
                        showEmailAuth = true
                    } label: {
                        HStack(spacing: 10) {
                            Image(systemName: "envelope.fill")
                                .font(.system(size: 18))
                            Text("Продолжить по email")
                                .font(.system(size: 16, weight: .semibold))
                        }
                        .frame(maxWidth: .infinity)
                        .frame(height: 50)
                        .foregroundColor(.white)
                        .background(Color(red: 0.15, green: 0.18, blue: 0.22))
                        .cornerRadius(12)
                    }
                }
                .padding(.horizontal, 24)

                // Error message
                if case .error(let message) = authManager.state {
                    Text(message)
                        .font(.system(size: 13))
                        .foregroundColor(.red)
                        .multilineTextAlignment(.center)
                        .padding(.horizontal, 24)
                        .padding(.top, 16)
                }

                Spacer()
                    .frame(height: 32)

                // Terms
                Text("Продолжая, вы соглашаетесь с\nУсловиями использования и Политикой конфиденциальности")
                    .font(.system(size: 11))
                    .foregroundColor(.gray.opacity(0.7))
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 24)
                    .padding(.bottom, 24)
            }
        }
        .sheet(isPresented: $showEmailAuth) {
            EmailAuthSheet()
        }
    }
}

// MARK: - Apple Sign In Button

private struct AppleSignInButton: View {
    @StateObject private var authManager = AuthManager.shared
    @State private var currentNonceHash: String = ""

    var body: some View {
        SignInWithAppleButton(.signIn) { request in
            currentNonceHash = authManager.prepareAppleSignIn()
            request.requestedScopes = [.fullName, .email]
            request.nonce = currentNonceHash
        } onCompletion: { result in
            switch result {
            case .success(let authorization):
                Task {
                    await authManager.handleAppleAuthorization(authorization)
                }
            case .failure(let error):
                authManager.handleAppleError(error)
            }
        }
        .signInWithAppleButtonStyle(.white)
        .frame(height: 50)
        .cornerRadius(12)
    }
}

// MARK: - Google Sign In Button

private struct GoogleSignInButton: View {
    @StateObject private var authManager = AuthManager.shared

    var body: some View {
        Button {
            Task {
                await authManager.signInWithGoogle()
            }
        } label: {
            HStack(spacing: 10) {
                // Google "G" logo approximation
                ZStack {
                    Circle()
                        .fill(.white)
                        .frame(width: 20, height: 20)

                    Text("G")
                        .font(.system(size: 14, weight: .bold))
                        .foregroundColor(.blue)
                }

                Text("Продолжить с Google")
                    .font(.system(size: 16, weight: .semibold))
            }
            .frame(maxWidth: .infinity)
            .frame(height: 50)
            .foregroundColor(.white)
            .background(Color(red: 0.25, green: 0.30, blue: 0.38))
            .cornerRadius(12)
        }
    }
}

// MARK: - Email Auth Sheet

private struct EmailAuthSheet: View {
    @Environment(\.dismiss) private var dismiss
    @StateObject private var authManager = AuthManager.shared

    @State private var email = ""
    @State private var code = ""
    @State private var challengeId: String?
    @State private var isLoading = false
    @State private var errorText: String?

    // Resend cooldown
    @State private var resendCooldown: Int = 0
    @State private var resendTimer: Timer?
    @FocusState private var focusedField: EmailAuthField?

    var body: some View {
        NavigationView {
            VStack(spacing: 20) {
                // Header
                VStack(spacing: 8) {
                    Image(systemName: challengeId == nil ? "envelope.fill" : "lock.fill")
                        .font(.system(size: 40, weight: .medium))
                        .foregroundColor(.travelBuddyOrange)

                    Text(challengeId == nil ? "Введите email" : "Введите код из письма")
                        .font(.system(size: 20, weight: .semibold))

                    if challengeId != nil {
                        Text("Код отправлен на \(email)")
                            .font(.system(size: 13))
                            .foregroundColor(.secondary)
                    }
                }
                .padding(.top, 20)

                // Input field
                if challengeId == nil {
                    // Email input
                    TextField("email@example.com", text: $email)
                        .keyboardType(.emailAddress)
                        .textContentType(.emailAddress)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .focused($focusedField, equals: .email)
                        .padding(14)
                        .background(Color(.secondarySystemBackground))
                        .cornerRadius(12)
                } else {
                    // Code input
                    TextField("000000", text: $code)
                        .keyboardType(.numberPad)
                        .multilineTextAlignment(.center)
                        .font(.system(size: 24, weight: .semibold, design: .monospaced))
                        .focused($focusedField, equals: .code)
                        .padding(14)
                        .background(Color(.secondarySystemBackground))
                        .cornerRadius(12)
                        .onChange(of: code) { _, newValue in
                            // Limit to 6 digits
                            if newValue.count > 6 {
                                code = String(newValue.prefix(6))
                            }
                            // Only allow digits
                            code = newValue.filter { $0.isNumber }
                        }
                }

                // Error text
                if let errorText {
                    Text(errorText)
                        .font(.system(size: 13))
                        .foregroundColor(.red)
                        .multilineTextAlignment(.center)
                }

                // Primary action button
                Button {
                    Task {
                        await handlePrimaryAction()
                    }
                } label: {
                    Group {
                        if isLoading {
                            ProgressView()
                                .tint(.white)
                        } else {
                            Text(challengeId == nil ? "Отправить код" : "Подтвердить")
                                .font(.system(size: 16, weight: .semibold))
                        }
                    }
                    .frame(maxWidth: .infinity)
                    .frame(height: 50)
                    .background(primaryButtonEnabled ? Color.travelBuddyOrange : Color.gray)
                    .foregroundColor(.white)
                    .cornerRadius(12)
                }
                .disabled(!primaryButtonEnabled || isLoading)

                // Resend button (only shown after code was sent)
                if challengeId != nil {
                    Button {
                        Task {
                            await resendCode()
                        }
                    } label: {
                        if resendCooldown > 0 {
                            Text("Отправить повторно через \(resendCooldown) сек")
                                .font(.system(size: 14))
                                .foregroundColor(.gray)
                        } else {
                            Text("Отправить код повторно")
                                .font(.system(size: 14, weight: .medium))
                                .foregroundColor(.travelBuddyOrange)
                        }
                    }
                    .disabled(resendCooldown > 0 || isLoading)
                }

                Spacer()
            }
            .padding(.horizontal, 24)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Button("Закрыть") {
                        dismiss()
                    }
                }

                if challengeId != nil {
                    ToolbarItem(placement: .navigationBarTrailing) {
                        Button("Назад") {
                            challengeId = nil
                            code = ""
                            errorText = nil
                            stopResendTimer()
                        }
                    }
                }
            }
        }
        .onDisappear {
            stopResendTimer()
        }
        .onAppear {
            focusedField = .email
        }
        .onChange(of: challengeId) { _, newValue in
            focusedField = newValue == nil ? .email : .code
        }
    }

    private var primaryButtonEnabled: Bool {
        if challengeId == nil {
            return isValidEmail(email)
        } else {
            return code.count == 6
        }
    }

    private func isValidEmail(_ email: String) -> Bool {
        let emailRegex = #"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$"#
        return email.range(of: emailRegex, options: .regularExpression) != nil
    }

    @MainActor
    private func handlePrimaryAction() async {
        errorText = nil
        isLoading = true

        do {
            if challengeId == nil {
                // Request code
                let challenge = try await authManager.requestEmailCode(email: email)
                challengeId = challenge
                startResendCooldown()
            } else {
                // Verify code
                await authManager.verifyEmailCode(challengeId: challengeId!, code: code)

                // Check if auth succeeded
                if case .loggedIn = authManager.state {
                    dismiss()
                } else if case .error(let message) = authManager.state {
                    errorText = message
                }
            }
        } catch {
            errorText = (error as? LocalizedError)?.errorDescription ?? "Ошибка авторизации"
        }

        isLoading = false
    }

    @MainActor
    private func resendCode() async {
        errorText = nil
        isLoading = true

        do {
            let challenge = try await authManager.requestEmailCode(email: email)
            challengeId = challenge
            startResendCooldown()
        } catch {
            errorText = (error as? LocalizedError)?.errorDescription ?? "Не удалось отправить код"
        }

        isLoading = false
    }

    private func startResendCooldown() {
        resendCooldown = 30
        resendTimer = Timer.scheduledTimer(withTimeInterval: 1, repeats: true) { _ in
            if resendCooldown > 0 {
                resendCooldown -= 1
            } else {
                stopResendTimer()
            }
        }
    }

    private func stopResendTimer() {
        resendTimer?.invalidate()
        resendTimer = nil
        resendCooldown = 0
    }
}

private enum EmailAuthField {
    case email
    case code
}
