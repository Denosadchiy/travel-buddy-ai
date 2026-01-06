//
//  RemoteImageView.swift
//  Travell Buddy
//
//  Lightweight remote image loader with in-memory cache.
//

import SwiftUI

private final class RemoteImageCache {
    static let shared = RemoteImageCache()
    private let cache = NSCache<NSURL, UIImage>()

    func image(for url: NSURL) -> UIImage? {
        cache.object(forKey: url)
    }

    func store(_ image: UIImage, for url: NSURL) {
        cache.setObject(image, forKey: url)
    }
}

private final class RemoteImageLoader: ObservableObject {
    @Published var image: UIImage?
    private var task: URLSessionDataTask?

    func load(from url: URL?) {
        task?.cancel()
        image = nil

        guard let url else { return }
        let nsURL = url as NSURL

        if let cached = RemoteImageCache.shared.image(for: nsURL) {
            image = cached
            return
        }

        let request = URLRequest(url: url, cachePolicy: .returnCacheDataElseLoad, timeoutInterval: 30)
        task = URLSession.shared.dataTask(with: request) { [weak self] data, response, error in
            guard
                let self,
                let data,
                let httpResponse = response as? HTTPURLResponse,
                200..<300 ~= httpResponse.statusCode,
                let uiImage = UIImage(data: data),
                error == nil
            else {
                return
            }

            RemoteImageCache.shared.store(uiImage, for: nsURL)
            DispatchQueue.main.async {
                self.image = uiImage
            }
        }
        task?.resume()
    }
}

struct RemoteImageView: View {
    let url: URL?

    @StateObject private var loader = RemoteImageLoader()

    var body: some View {
        Group {
            if let image = loader.image {
                Image(uiImage: image)
                    .resizable()
                    .scaledToFill()
            } else {
                Color.clear
            }
        }
        .onAppear {
            loader.load(from: url)
        }
        .onChange(of: url) { newValue in
            loader.load(from: newValue)
        }
    }
}
