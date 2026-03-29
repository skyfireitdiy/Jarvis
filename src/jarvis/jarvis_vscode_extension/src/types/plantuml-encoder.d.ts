declare module "plantuml-encoder" {
  const plantumlEncoder: {
    encode(source: string): string;
  };

  export default plantumlEncoder;
}
