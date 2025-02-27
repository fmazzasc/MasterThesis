// Spectra.cpp
// This macro computes fully corrected spectra

#include <Riostream.h>
#include <TFile.h>
#include <TH1D.h>
#include <TH2F.h>
#include <TStyle.h>
#include <TLatex.h>

#include "Utils.h"
#include "Config.h"

using utils::TTList;

void Spectra(const float cutDCAz = 1.f, const int cutTPCcls = 89, const bool binCounting = true, const int bkg_shape = 1, const bool sigmoidCorrection = true, const char *histoNameDir = ".", const char *outFileName = "SpectraHe3", const char *outFileOption = "recreate", const char *dataFile = "AnalysisResults", const char *signalFile = "SignalHe3", const char *effFile = "EfficiencyHe3", const char *primFile = "PrimaryHe3")
{
  gStyle->SetOptFit(1111);

  TH2F *fNevents[kNDataFiles];
  for (int iD = 0; iD < kNDataFiles; ++iD)
  {
    TFile *inFileDat = TFile::Open(Form("%s/%s_%s.root", kDataDir, dataFile, kDataFileLabel[iD]));
    TTList *fMultList = (TTList *)inFileDat->Get("mpuccio_he3_");
    fNevents[iD] = (TH2F *)fMultList->Get("fNormalisationHist");
  }
  TFile *inFileRaw = TFile::Open(Form("%s/%s.root", kOutDir, signalFile));
  TFile *inFileEff = TFile::Open(Form("%s/%s.root", kOutDir, effFile));
  TFile *inFileSec = TFile::Open(Form("%s/%s.root", kOutDir, primFile));
  TFile outFile(Form("%s/%s.root", kOutDir, outFileName), outFileOption);

  outFile.mkdir(histoNameDir);

  TH1D *fRatio[kNCentClasses];
  for (int iCent = 0; iCent < kNCentClasses; ++iCent)
  {
    fRatio[iCent] = new TH1D(*(TH1D *)inFileRaw->Get(Form("%1.1f_%d_%d_%d/fATPCrawYield_%.0f_%.0f", cutDCAz, cutTPCcls, binCounting, bkg_shape, kCentBinsLimitsHe3[iCent][0], kCentBinsLimitsHe3[iCent][1])));
    fRatio[iCent]->Reset();
    fRatio[iCent]->SetName(Form("fRatio_%.0f_%.0f", kCentBinsLimitsHe3[iCent][0], kCentBinsLimitsHe3[iCent][1]));
    fRatio[iCent]->SetTitle("");
  }

  TH1D *fSpectra[2];
  for (int iCent = 0; iCent < kNCentClasses; ++iCent)
  {
    TH1D *norm[2];
    for (int iD = 0; iD < kNDataFiles; ++iD)
      norm[iD] = fNevents[iD]->ProjectionY("norm", kCentBinsHe3[iCent][0], kCentBinsHe3[iCent][1]);

    // compute corrected spectra
    for (int iMatt = 0; iMatt < 2; ++iMatt)
    {
      outFile.cd(histoNameDir);
      TH1D *eff = (TH1D *)inFileEff->Get(Form("f%sEff_TPC_%.0f_%.0f", kAntimatterMatter[iMatt], kCentBinsLimitsHe3[iCent][0], kCentBinsLimitsHe3[iCent][1]));
      TF1 *sec_f = (TF1 *)inFileSec->Get(Form("f%sSigmoidFit_%.0f_%.0f", kAntimatterMatter[iMatt], kCentBinsLimitsHe3[iCent][0], kCentBinsLimitsHe3[iCent][1]));
      TH1D *sec = (TH1D *)inFileSec->Get(Form("f%sPrimFrac_%.0f_%.0f", kAntimatterMatter[iMatt], kCentBinsLimitsHe3[iCent][0], kCentBinsLimitsHe3[iCent][1]));
      TH1D *raw = (TH1D *)inFileRaw->Get(Form("%1.1f_%d_%d_%d/f%sTPCrawYield_%.0f_%.0f", cutDCAz, cutTPCcls, binCounting, bkg_shape, kAntimatterMatter[iMatt], kCentBinsLimitsHe3[iCent][0], kCentBinsLimitsHe3[iCent][1]));

      //sec->Fit(&fitFuncSec,"R");
      fSpectra[iMatt] = new TH1D(*eff);
      int pTbinMax = 11;
      if (iCent < kNCentClasses - 1)
        pTbinMax = 13;
      fSpectra[iMatt]->Reset();
      for (int iPtBin = 3; iPtBin < pTbinMax + 1; ++iPtBin)
      {
        double rawYield = raw->GetBinContent(iPtBin);
        double rawYieldError = raw->GetBinError(iPtBin);
        double efficiency = eff->GetBinContent(iPtBin);
        double effError = eff->GetBinError(iPtBin);

        double primary = 0.;
        (!sigmoidCorrection && raw->GetBinCenter(iPtBin) < 6.3) ? primary = sec->GetBinContent(iPtBin) : primary = sec_f->Eval(raw->GetXaxis()->GetBinCenter(iPtBin));
        fSpectra[iMatt]->SetBinContent(iPtBin, rawYield * primary / efficiency);
        fSpectra[iMatt]->SetBinError(iPtBin, rawYield * primary / efficiency * TMath::Sqrt(effError * effError / efficiency / efficiency + rawYieldError * rawYieldError / rawYield / rawYield));
      }
      fSpectra[iMatt]->SetName(Form("f%sSpectra_%.0f_%.0f", kAntimatterMatter[iMatt], kCentBinsLimitsHe3[iCent][0], kCentBinsLimitsHe3[iCent][1]));
      fSpectra[iMatt]->SetTitle(Form("%s, %.0f-%.0f%%", kAntimatterMatterLabel[iMatt], kCentBinsLimitsHe3[iCent][0], kCentBinsLimitsHe3[iCent][1]));
      fSpectra[iMatt]->GetYaxis()->SetTitle("1/#it{N}_{ev} d^{2}#it{N}/d#it{p}_{T}d#it{y} (GeV/#it{c})^{-1}");
      fSpectra[iMatt]->GetXaxis()->SetTitle(kAxisTitlePt);

      // scale by number of events
      double events = 0.f;
      for (int iD = 0; iD < kNDataFiles; ++iD)
        events += norm[iD]->GetBinContent(4);
      fSpectra[iMatt]->Scale(1. / events, "width");

      // write to file
      fSpectra[iMatt]->Write();
    }

    // compute ratios
    int pTbinMax = 11;
    if (iCent < kNCentClasses - 1)
      pTbinMax = 13;
    for (int iPtBin = 3; iPtBin < pTbinMax + 1; ++iPtBin)
    {
      double antiSpec = fSpectra[0]->GetBinContent(iPtBin);
      double spec = fSpectra[1]->GetBinContent(iPtBin);
      double antiSpecErr = fSpectra[0]->GetBinError(iPtBin);
      double specErr = fSpectra[1]->GetBinError(iPtBin);
      if (spec > 1.e-10)
      {
        fRatio[iCent]->SetBinContent(iPtBin, antiSpec / spec);
        fRatio[iCent]->SetBinError(iPtBin, antiSpec / spec * TMath::Sqrt(antiSpecErr * antiSpecErr / antiSpec / antiSpec + specErr * specErr / spec / spec));
      }
    }
    fRatio[iCent]->GetXaxis()->SetTitle(kAxisTitlePt);
    fRatio[iCent]->GetYaxis()->SetTitle(Form("%s/%s", kAntimatterMatterLabel[0], kAntimatterMatterLabel[1]));
    gStyle->SetOptFit(1111);
    fRatio[iCent]->SetTitle(Form("%.0f-%.0f%%", kCentBinsLimitsHe3[iCent][0], kCentBinsLimitsHe3[iCent][1]));
    fRatio[iCent]->Fit("pol0");
    fRatio[iCent]->Write();
  }
  outFile.Close();
}