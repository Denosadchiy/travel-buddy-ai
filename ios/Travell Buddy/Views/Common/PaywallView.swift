//
//  PaywallView.swift
//  Travell Buddy
//
//  Paywall modal shown for locked actions (e.g., viewing full itinerary).
//  Uses AuthManager for consistent auth state management.
//

import SwiftUI
import AuthenticationServices

struct PaywallView: View {
    let subtitle: String?
    let dayNumber: Int?
    let unlockedFeaturesLabel: String
    let footerText: String
    let onAuthSuccess: () -> Void

    @Environment(\.dismiss) private var dismiss
    @StateObject private var authManager = AuthManager.shared
    @State private var isShowingEmailAuth: Bool = false
    @State private var isLoading: Bool = false
    @State private var errorText: String?
    @State private var currentNonceHash: String = ""
    @State private var activeProvider: ActiveAuthProvider?

    init(
        subtitle: String? = nil,
        dayNumber: Int? = nil,
        unlockedFeaturesLabel: String = "карта + полные маршрут",
        footerText: String = "Вход нужен, чтобы открыть карту и остальные дни",
        onAuthSuccess: @escaping () -> Void
    ) {
        self.subtitle = subtitle
        self.dayNumber = dayNumber
        self.unlockedFeaturesLabel = unlockedFeaturesLabel
        self.footerText = footerText
        self.onAuthSuccess = onAuthSuccess
    }

    var body: some View {
        UnlockAuthSheetView(
            dayNumber: dayNumber,
            unlockedFeaturesLabel: unlockedFeaturesLabel,
            subtitle: subtitle,
            footerText: footerText,
            isLoading: isLoading,
            isAppleLoading: isLoading && activeProvider == .apple,
            isGoogleLoading: isLoading && activeProvider == .google,
            errorText: errorText,
            onClose: {
                errorText = nil
                dismiss()
            },
            onAppleRequest: { request in
                activeProvider = .apple
                currentNonceHash = authManager.prepareAppleSignIn()
                request.requestedScopes = [.fullName, .email]
                request.nonce = currentNonceHash
            },
            onAppleCompletion: handleAppleResult,
            onEmail: {
                errorText = nil
                isShowingEmailAuth = true
            },
            onGoogle: {
                errorText = nil
                activeProvider = .google
                Task {
                    await handleGoogleSignIn()
                }
            }
        )
        .sheet(isPresented: $isShowingEmailAuth) {
            PaywallEmailAuthView(onComplete: {
                onAuthSuccess()
            })
        }
        .onChange(of: authManager.state) { _, newState in
            // React to auth state changes from AuthManager
            switch newState {
            case .loggedIn:
                activeProvider = nil
                onAuthSuccess()
            case .error(let message):
                errorText = message
                isLoading = false
                activeProvider = nil
            case .loggingIn:
                isLoading = true
            default:
                isLoading = false
                activeProvider = nil
            }
        }
    }

    private func handleAppleResult(_ result: Result<ASAuthorization, Error>) {
        switch result {
        case .success(let authorization):
            Task {
                await authManager.handleAppleAuthorization(authorization)
            }
        case .failure(let error):
            authManager.handleAppleError(error)
        }
    }

    @MainActor
    private func handleGoogleSignIn() async {
        await authManager.signInWithGoogle()
    }
}

private enum ActiveAuthProvider {
    case apple
    case google
}

// MARK: - Paywall Email Auth View

private struct PaywallEmailAuthView: View {
    let onComplete: () -> Void

    @Environment(\.dismiss) private var dismiss
    @StateObject private var authManager = AuthManager.shared
    @State private var email: String = ""
    @State private var code: String = ""
    @State private var challengeId: String?
    @State private var isLoading: Bool = false
    @State private var errorText: String?
    @State private var resendCooldown: Int = 0
    @State private var resendTimer: Timer?
    @FocusState private var focusedField: EmailAuthField?

    var body: some View {
        NavigationView {
            VStack(spacing: 16) {
                // Header
                VStack(spacing: 8) {
                    Image(systemName: challengeId == nil ? "envelope.fill" : "lock.fill")
                        .font(.system(size: 36, weight: .medium))
                        .foregroundColor(.travelBuddyOrange)

                    Text(challengeId == nil ? "Введите email" : "Введите код из письма")
                        .font(.system(size: 18, weight: .semibold))

                    if challengeId != nil {
                        Text("Код отправлен на \(email)")
                            .font(.system(size: 13))
                            .foregroundColor(.secondary)
                    }
                }
                .padding(.top, 16)

                // Input field
                if challengeId == nil {
                    TextField("email@example.com", text: $email)
                        .keyboardType(.emailAddress)
                        .textContentType(.emailAddress)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .focused($focusedField, equals: .email)
                        .padding(12)
                        .background(Color(.secondarySystemBackground))
                        .cornerRadius(10)
                } else {
                    TextField("000000", text: $code)
                        .keyboardType(.numberPad)
                        .multilineTextAlignment(.center)
                        .font(.system(size: 20, weight: .semibold, design: .monospaced))
                        .focused($focusedField, equals: .code)
                        .padding(12)
                        .background(Color(.secondarySystemBackground))
                        .cornerRadius(10)
                        .onChange(of: code) { _, newValue in
                            if newValue.count > 6 {
                                code = String(newValue.prefix(6))
                            }
                            code = newValue.filter { $0.isNumber }
                        }
                }

                if let errorText {
                    Text(errorText)
                        .font(.system(size: 13))
                        .foregroundColor(.red)
                        .multilineTextAlignment(.center)
                }

                // Primary action button
                Button {
                    Task { await handlePrimaryAction() }
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
                    .frame(height: 48)
                    .background(primaryButtonEnabled ? Color.travelBuddyOrange : Color.gray)
                    .foregroundColor(.white)
                    .cornerRadius(12)
                }
                .disabled(!primaryButtonEnabled || isLoading)

                // Resend button
                if challengeId != nil {
                    Button {
                        Task { await resendCode() }
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
            .padding(24)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Button("Закрыть") { dismiss() }
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
        .onChange(of: authManager.state) { _, newState in
            if case .loggedIn = newState {
                dismiss()
                onComplete()
            }
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
                let challenge = try await authManager.requestEmailCode(email: email)
                challengeId = challenge
                startResendCooldown()
            } else if let challengeId {
                await authManager.verifyEmailCode(challengeId: challengeId, code: code)
                // State change handled by onChange
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
