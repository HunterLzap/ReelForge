import { Config } from "@remotion/cli/config";

Config.overrideFfmpegCommand(({ args }) => {
  const threads = process.env.REELFORGE_ENCODER_THREADS;
  return threads
    ? [...args.slice(0, -1), "-threads", threads, args[args.length - 1]]
    : args;
});
