import type { ReadInputBarcodeFormat, ReadOutputBarcodeFormat } from "zxing-wasm/reader";
export type CanvasImageSourceWebCodecs = HTMLOrSVGImageElement | HTMLVideoElement | HTMLCanvasElement | ImageBitmap | OffscreenCanvas | VideoFrame;
export type ImageBitmapSourceWebCodecs = CanvasImageSourceWebCodecs | Blob | ImageData;
export declare const BARCODE_FORMATS: ("aztec" | "aztec_code" | "aztec_rune" | "code_128" | "code_39" | "code_39_standard" | "code_39_extended" | "code_32" | "pzn" | "code_93" | "codabar" | "databar" | "databar_omni" | "databar_stacked" | "databar_stacked_omni" | "databar_expanded" | "databar_expanded_stacked" | "databar_limited" | "data_matrix" | "dx_film_edge" | "ean_13" | "ean_upc" | "isbn" | "ean_8" | "itf" | "itf_14" | "maxi_code" | "micro_qr_code" | "pdf417" | "compact_pdf417" | "qr_code" | "qr_code_model_1" | "qr_code_model_2" | "rm_qr_code" | "upc_a" | "upc_e" | "other_barcode" | "linear_codes" | "matrix_codes" | "gs1_codes" | "retail_codes" | "industrial_codes" | "any" | "unknown")[];
export type BarcodeFormat = (typeof BARCODE_FORMATS)[number];
export type ReadResultBarcodeFormat = Exclude<BarcodeFormat, "linear_codes" | "matrix_codes" | "gs1_codes" | "retail_codes" | "industrial_codes" | "any">;
export declare const formatMap: Map<"aztec" | "aztec_code" | "aztec_rune" | "code_128" | "code_39" | "code_39_standard" | "code_39_extended" | "code_32" | "pzn" | "code_93" | "codabar" | "databar" | "databar_omni" | "databar_stacked" | "databar_stacked_omni" | "databar_expanded" | "databar_expanded_stacked" | "databar_limited" | "data_matrix" | "dx_film_edge" | "ean_13" | "ean_upc" | "isbn" | "ean_8" | "itf" | "itf_14" | "maxi_code" | "micro_qr_code" | "pdf417" | "compact_pdf417" | "qr_code" | "qr_code_model_1" | "qr_code_model_2" | "rm_qr_code" | "upc_a" | "upc_e" | "other_barcode" | "linear_codes" | "matrix_codes" | "gs1_codes" | "retail_codes" | "industrial_codes" | "any" | "unknown", ReadInputBarcodeFormat>;
export declare function convertFormat(target: ReadOutputBarcodeFormat): ReadResultBarcodeFormat;
export declare function isBlob(image: ImageBitmapSourceWebCodecs): image is Blob;
export declare function getImageDataOrBlobFromImageBitmapSource(image: ImageBitmapSourceWebCodecs): Promise<ImageData | Blob | null>;
declare global {
    interface SVGImageElement {
        decode?(): Promise<void>;
    }
}
export declare function addPrefixToExceptionOrError(e: unknown, prefix: string): TypeError | DOMException;
